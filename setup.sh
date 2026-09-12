#!/usr/bin/env bash
# One-shot setup for this Claude Code environment on Linux (native or
# under WSL2) and macOS.
# Installs what it can, registers what it can into ~/.claude.json, and
# prints exactly what's left for you to do by hand (secrets, Bifrost UI).
#
# Optional config via env vars or a repo-root .env file (see .env.example):
#   GITHUB_TOKEN, OBSIDIAN_VAULT_PATH,
#   SKIP_FIRECRAWL=1, SKIP_BIFROST=1, SKIP_LIGHTPANDA=1
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Parsed line-by-line rather than `source`d: sourcing runs .env as real
# bash, so an unquoted value with a space (e.g. a Windows-style
# OBSIDIAN_VAULT_PATH like "C:\Users\you\Documents\My Vault") gets
# word-split and the trailing word executed as a command, and backslashes
# get interpreted as escapes - both silently corrupt the value. Reading it
# as plain text keeps spaces and backslashes literal with no quoting needed.
if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*(#.*)?$ ]] && continue
    [[ "$line" == *=* ]] || continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key//[[:space:]]/}"
    if [[ ("$value" == \"*\" && "$value" == *\") || ("$value" == \'*\' && "$value" == *\') ]]; then
      value="${value:1:-1}"
    fi
    export "$key=$value"
  done < .env
fi

# gum is cosmetic only - if it can't be found or downloaded, everything
# below falls back to plain output instead of failing the whole setup.
# Resolution is silent; nothing is printed either way.
GUM=""
GUM_TMP_DIR=""
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/ensure-gum.sh"
[ -n "$GUM_TMP_DIR" ] && trap 'rm -rf "$GUM_TMP_DIR"' EXIT

step() {
  if [ -n "$GUM" ]; then echo; "$GUM" style --foreground 212 "==> $1"
  else printf '\n\033[1m==> %s\033[0m\n' "$1"; fi
}
ok()   { if [ -n "$GUM" ]; then "$GUM" style --foreground 2 "  ✓ $1";   else printf '  ok   %s\n' "$1"; fi; }
skip() { if [ -n "$GUM" ]; then "$GUM" style --foreground 8 "  - $1";   else printf '  skip %s\n' "$1"; fi; }
warn() { if [ -n "$GUM" ]; then "$GUM" style --foreground 3 "  ! $1" >&2; else printf '  warn %s\n' "$1" >&2; fi; }
# gum's TUI runs the terminal in raw mode, so Ctrl+C there is a keystroke
# gum interprets itself (exit 130), not a signal that would stop this
# script - so every gum confirm/spin call is checked for it explicitly.
quit_setup() {
  echo
  if [ -n "$GUM" ]; then "$GUM" style --foreground 1 "Setup cancelled."
  else echo "Setup cancelled."; fi
  exit 130
}
# Runs "$@" with a spinner; output only surfaces if the command fails.
# Quits the whole setup (not just this step) if Ctrl+C was pressed.
# --spinner line: plain ASCII (-\|/), not gum's default Braille-dot frames,
# which render as mangled boxes in terminals/fonts without that Unicode block.
spin() {
  local title="$1" rc; shift
  if [ -n "$GUM" ]; then
    "$GUM" spin --spinner line --title "$title" --show-error -- "$@"; rc=$?
    [ "$rc" -eq 130 ] && quit_setup
    return "$rc"
  else
    echo "  ... $title"; "$@"
  fi
}
# Asks a y/n question via gum (or a plain read as fallback); returns 0 for
# yes, 1 for no. Quits the whole setup (not just this step) on Ctrl+C.
confirm() {
  if [ -n "$GUM" ]; then
    "$GUM" confirm "$1"; local rc=$?
    [ "$rc" -eq 130 ] && quit_setup
    return "$rc"
  else
    local reply
    read -r -p "  $1 [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
  fi
}

step "Git commit-msg hook"
if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$REPO_ROOT" config core.hooksPath githooks
  ok "commit-msg now enforces Conventional Commits (see githooks/commit-msg)"
else
  skip "not a git checkout"
fi

step "Checking required tools"
command -v node >/dev/null || { echo "node is required - install it first (https://nodejs.org)"; exit 1; }
command -v npx  >/dev/null || { echo "npx is required (ships with node >=8.2)"; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required for scripts/merge-mcp-config.py"; exit 1; }
ok "node $(node --version), npx $(npx --version), $(python3 --version)"

HAS_DOCKER=false
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  HAS_DOCKER=true
  ok "docker $(docker --version | cut -d, -f1)"
else
  warn "docker not available - Firecrawl self-host will be skipped (see docs/DECISIONS.md)"
fi

export HAS_UVX=false
if command -v uvx >/dev/null; then
  export HAS_UVX=true
  ok "uvx $(uvx --version)"
else
  warn "uvx not available - browser-use (self-hosted) will be skipped (install: https://docs.astral.sh/uv/)"
fi

OS_NAME="$(uname -s)"
CAN_USE_LIGHTPANDA=false
[ "$OS_NAME" = "Linux" ] || [ "$OS_NAME" = "Darwin" ] && CAN_USE_LIGHTPANDA=true

step "Codegraph"
if ! command -v codegraph >/dev/null; then
  spin "Installing codegraph..." bash -c "curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh"
  export PATH="$HOME/.local/bin:$PATH"
fi
if command -v codegraph >/dev/null; then
  # codegraph's own installer prints a multi-line status box (its own
  # terminal UI, not ours) - spin hides it and only surfaces it on failure.
  spin "Registering codegraph in Claude Code..." codegraph install --target claude --location global -y
  ok "codegraph $(codegraph version 2>/dev/null || echo installed) registered in Claude Code"

  if [ -d "$REPO_ROOT/.codegraph" ]; then
    CG_ACTION=sync; CG_PROMPT="Sync codegraph's index for this repo now (codegraph sync)?"; CG_SKIP_MSG="not synced"
  else
    CG_ACTION=init; CG_PROMPT="Index this repo with codegraph now (codegraph init)?"; CG_SKIP_MSG="not indexed"
  fi
  if [ ! -t 0 ]; then
    echo "  Run 'codegraph $CG_ACTION' in this repo (or any project) whenever you want to build/refresh its index."
  elif confirm "$CG_PROMPT"; then
    spin "Running codegraph $CG_ACTION..." codegraph "$CG_ACTION"
    ok "codegraph $CG_ACTION complete"
  else
    skip "$CG_SKIP_MSG - run 'codegraph $CG_ACTION' in this repo anytime"
  fi
else
  warn "codegraph install failed - skipping registration"
fi

step "browser-use (self-hosted, Claude-driven browser control)"
if [ "$HAS_UVX" = true ]; then
  ok "will register (see summary below for the one-time Chromium install)"
else
  skip "uvx not available"
fi

step "librarian-mcp (Obsidian)"
if ! command -v librarian-mcp >/dev/null; then
  spin "Installing librarian-mcp..." bash -c "curl -fsSL https://github.com/ngmeyer/librarian-mcp/releases/latest/download/librarian-mcp-installer.sh | sh"
  export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
fi
if command -v librarian-mcp >/dev/null; then
  ok "librarian-mcp installed"
  if [ -z "${OBSIDIAN_VAULT_PATH:-}" ]; then
    warn "OBSIDIAN_VAULT_PATH not set - obsidian MCP entry will be skipped"
  elif [ ! -d "$OBSIDIAN_VAULT_PATH" ]; then
    warn "OBSIDIAN_VAULT_PATH is not an existing directory: $OBSIDIAN_VAULT_PATH - obsidian MCP entry will be skipped (under WSL2, a Windows-side vault needs /mnt/c/... not C:\\...)"
  fi
else
  warn "librarian-mcp install failed - obsidian MCP entry will be skipped"
fi

step "Lightpanda (fast local browser engine)"
export HAS_LIGHTPANDA=false
if [ "$CAN_USE_LIGHTPANDA" = true ] && [ "${SKIP_LIGHTPANDA:-}" != "1" ]; then
  if ! command -v lightpanda >/dev/null; then
    spin "Installing lightpanda..." bash -c "curl -fsSL https://pkg.lightpanda.io/install.sh | bash"
    export PATH="$HOME/.local/bin:$PATH"
  fi
  if command -v lightpanda >/dev/null; then
    ok "lightpanda installed"
    export HAS_LIGHTPANDA=true
  else
    warn "lightpanda install failed - lightpanda-playwright MCP entry will be skipped"
  fi
else
  skip "not supported on $OS_NAME without WSL (lightpanda has no native Windows build yet)"
fi

step "CLAUDE.md for this repo"
PROMPT_FILE="$REPO_ROOT/claude-md/init-prompt.md"
show_prompt() {
  echo "  $1"
  if [ -n "$GUM" ]; then "$GUM" format <"$PROMPT_FILE"
  else echo "  ----------------------------------------------------------------"; cat "$PROMPT_FILE"; echo "  ----------------------------------------------------------------"; fi
}
if [ -f "$REPO_ROOT/CLAUDE.md" ]; then
  skip "CLAUDE.md already exists - not touching it"
elif [ ! -t 0 ]; then
  show_prompt "Not an interactive terminal - here's the prompt, paste it into any Claude Code session when you're ready:"
elif confirm "Initialize CLAUDE.md for this repo now with Claude Code?"; then
  if command -v claude >/dev/null; then
    # --allowedTools "Edit(CLAUDE.md)" scopes write access to just this one
    # file, so claude -p can actually create it instead of stopping to ask
    # for permission (which, in a non-interactive -p run, it can't get -
    # it would otherwise print a conversational "may I write this?" and
    # never create the file). Output is captured, not streamed, and only
    # shown if CLAUDE.md doesn't actually exist afterward.
    CLAUDE_MD_LOG="$(mktemp)"
    claude -p "$(cat "$PROMPT_FILE")" --allowedTools "Edit(CLAUDE.md)" >"$CLAUDE_MD_LOG" 2>&1
    if [ -f "$REPO_ROOT/CLAUDE.md" ]; then
      ok "CLAUDE.md generated - review it"
    else
      warn "claude -p didn't create CLAUDE.md - see below, or use the prompt instead"
      cat "$CLAUDE_MD_LOG"
      show_prompt "Copy this into any Claude Code session (here or another project) whenever you want to generate a CLAUDE.md:"
    fi
    rm -f "$CLAUDE_MD_LOG"
  else
    warn "claude CLI not found on PATH - here's the prompt instead"
    show_prompt "Copy this into any Claude Code session (here or another project) whenever you want to generate a CLAUDE.md:"
  fi
else
  show_prompt "Copy this into any Claude Code session (here or another project) whenever you want to generate a CLAUDE.md:"
fi

step "Registering MCP servers into ~/.claude.json"
python3 "$REPO_ROOT/scripts/merge-mcp-config.py"

step "Firecrawl (self-hosted web scraping)"
if [ "$HAS_DOCKER" = true ] && [ "${SKIP_FIRECRAWL:-}" != "1" ]; then
  spin "Bringing up self-hosted Firecrawl..." bash "$REPO_ROOT/scripts/setup-firecrawl.sh" || warn "Firecrawl bring-up failed - see output above"
else
  skip "docker unavailable or SKIP_FIRECRAWL=1"
fi

step "Bifrost gateway"
if [ "${SKIP_BIFROST:-}" != "1" ]; then
  if curl -s -o /dev/null -w '%{http_code}' http://localhost:8080 2>/dev/null | grep -q 200; then
    ok "already running on http://localhost:8080"
  else
    nohup npx -y @maximhq/bifrost >/tmp/bifrost.log 2>&1 &
    disown
    ok "starting in background (log: /tmp/bifrost.log) - give it a few seconds"
  fi
else
  skip "SKIP_BIFROST=1"
fi

step "Summary - what's left for you"
SUMMARY="1. Open http://localhost:8080, finish Bifrost onboarding, generate a virtual key.
   claude mcp add --transport http bifrost http://localhost:8080/mcp --header \"Authorization: Bearer <key>\" --scope user
2. In the Bifrost UI, add downstream servers you'd rather gateway than run direct
   (command/args/env are in mcp/mcp-servers.json)."
[ -n "${GITHUB_TOKEN:-}${GITHUB_PERSONAL_ACCESS_TOKEN:-}" ] || SUMMARY="$SUMMARY
- Set GITHUB_TOKEN and re-run to register the GitHub MCP server."
if [ "$HAS_UVX" = true ]; then
  SUMMARY="$SUMMARY
- Run 'uvx --python 3.12 browser-use[cli] install' once before first using the browser-use MCP (installs Chromium, may prompt for sudo on Linux)."
else
  SUMMARY="$SUMMARY
- Install uv/uvx (https://docs.astral.sh/uv/) and re-run to enable the browser-use MCP server."
fi
if [ -z "${OBSIDIAN_VAULT_PATH:-}" ]; then
  SUMMARY="$SUMMARY
- Set OBSIDIAN_VAULT_PATH and re-run to register the Obsidian (librarian-mcp) server."
elif [ ! -d "$OBSIDIAN_VAULT_PATH" ]; then
  SUMMARY="$SUMMARY
- OBSIDIAN_VAULT_PATH ($OBSIDIAN_VAULT_PATH) is not an existing directory - fix it and re-run to register the Obsidian (librarian-mcp) server."
fi
SUMMARY="$SUMMARY
Run scripts/verify-env.sh anytime to recheck what's installed."

# Yellow (matches warn()'s color), deliberately not 212 like the step
# headers above - this is the "you still need to do something" list, so
# it should read as attention-needed, not blend in as just another step.
if [ -n "$GUM" ]; then "$GUM" style --foreground 3 "$SUMMARY"
else printf '\033[33m%s\033[0m\n' "$SUMMARY"; fi
