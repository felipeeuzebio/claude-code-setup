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

# Installers below drop binaries into these; prepended once up front so
# anything installed during this run is findable in this same shell.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

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
    # Strip one layer of matching quotes. Spelled with ${#value} instead of
    # a negative length so it also works on macOS's stock bash 3.2.
    case "$value" in
      \"*\" | \'*\') value="${value:1:${#value}-2}" ;;
    esac
    export "$key=$value"
  done <.env
fi

# gum is cosmetic only - if it can't be found or downloaded, everything
# below falls back to plain output instead of failing the whole setup.
# Resolution is silent; nothing is printed either way.
GUM=""
GUM_TMP_DIR=""
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/ensure-gum.sh"
[ -n "$GUM_TMP_DIR" ] && trap 'rm -rf "$GUM_TMP_DIR"' EXIT

# Every styled line goes through line() or block(). With gum: a colored
# glyph. Without: the same text behind a word label, legible with no color.
# line:  <gum color> <glyph> <plain label> <text>
# block: <gum color> <ANSI SGR code for the fallback> <text>
line() { if [ -n "$GUM" ]; then "$GUM" style --foreground "$1" -- "  $2 $4"; else printf '  %s %s\n' "$3" "$4"; fi; }
block() { if [ -n "$GUM" ]; then "$GUM" style --foreground "$1" -- "$3"; else printf '\033[%sm%s\033[0m\n' "$2" "$3"; fi; }
ok() { line 2 '✓' 'ok  ' "$1"; }
skip() { line 8 '-' 'skip' "$1"; }
warn() { line 3 '!' 'warn' "$1" >&2; }
step() {
  echo
  if [ -n "$GUM" ]; then "$GUM" style --foreground 212 -- "==> $1"; else printf '\033[1m==> %s\033[0m\n' "$1"; fi
}
# Like ok(), but prints the version dimmed so the tool name stands out.
# Color needs forcing here: capturing gum's output via $(...) hands it a
# pipe instead of our real stdout, so its own TTY check would otherwise
# decide color is unsupported and print plain text for both halves.
ok_ver() {
  if [ -z "$GUM" ]; then
    printf '  ok   %s %s\n' "$1" "$2"
    return
  fi
  local force=""
  [ -t 1 ] && force=1
  printf '%s%s\n' \
    "$(CLICOLOR_FORCE="$force" "$GUM" style --foreground 2 -- "  ✓ $1 ")" \
    "$(CLICOLOR_FORCE="$force" "$GUM" style --foreground 8 -- "$2")"
}
# gum's TUI runs the terminal in raw mode, so Ctrl+C there is a keystroke
# gum interprets itself (exit 130), not a signal that would stop this
# script - so every gum confirm/spin call is checked for it explicitly.
quit_setup() {
  echo
  block 1 31 "Setup cancelled."
  exit 130
}
# Runs "$@" with a spinner; output only surfaces if the command fails.
# --spinner line: plain ASCII (-\|/), not gum's default Braille-dot frames,
# which render as mangled boxes in terminals/fonts without that Unicode block.
spin() {
  local title="$1" rc
  shift
  if [ -z "$GUM" ]; then
    echo "  ... $title"
    "$@"
    return
  fi
  "$GUM" spin --spinner line --title "$title" --show-error -- "$@"
  rc=$?
  [ "$rc" -eq 130 ] && quit_setup
  return "$rc"
}
# Asks a y/n question; returns 0 for yes, 1 for no.
confirm() {
  if [ -z "$GUM" ]; then
    local reply
    read -r -p "  $1 [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
    return
  fi
  "$GUM" confirm -- "$1"
  local rc=$?
  [ "$rc" -eq 130 ] && quit_setup
  return "$rc"
}
# Exits the whole setup if $1 isn't on PATH, explaining why it's needed.
require() { command -v "$1" >/dev/null || {
  warn "$1 is required - $2"
  exit 1
}; }
# Installs $1 from the curl|bash installer at $2 unless it's already on
# PATH. Returns non-zero if the command still isn't available afterward.
install_tool() {
  command -v "$1" >/dev/null && return 0
  spin "Installing $1..." bash -c "curl -fsSL '$2' | bash"
  hash -r
  command -v "$1" >/dev/null
}

step "Git commit-msg hook"
if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$REPO_ROOT" config core.hooksPath githooks
  ok "commit-msg now enforces Conventional Commits (see githooks/commit-msg)"
else
  skip "Not a git checkout"
fi

step "Checking required tools"
require node "install it first (https://nodejs.org)"
require npx "it ships with node >=8.2"
require python3 "it runs scripts/merge-mcp-config.py (https://python.org)"
ok_ver node "$(node --version)"
ok_ver npx "$(npx --version)"
ok_ver python3 "$(python3 --version)"

HAS_DOCKER=false
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  HAS_DOCKER=true
  ok_ver docker "$(docker --version | cut -d, -f1)"
else
  warn "docker not available - Firecrawl self-host will be skipped (see AGENTS.md)"
fi

export HAS_UVX=false
if command -v uvx >/dev/null; then
  HAS_UVX=true
  ok_ver uvx "$(uvx --version)"
else
  warn "uvx not available - browser-use (self-hosted) will be skipped (install: https://docs.astral.sh/uv/)"
fi

step "Codegraph"
if install_tool codegraph https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh; then
  # codegraph's own installer prints a multi-line status box (its own
  # terminal UI, not ours) - spin hides it and only surfaces it on failure.
  spin "Registering codegraph in Claude Code..." codegraph install --target claude --location global -y
  ok "codegraph $(codegraph version 2>/dev/null || echo installed) registered in Claude Code"

  # init builds an index from scratch, sync refreshes the existing one.
  if [ -d "$REPO_ROOT/.codegraph" ]; then CG_ACTION=sync; else CG_ACTION=init; fi
  if [ ! -t 0 ]; then
    echo "  Run 'codegraph $CG_ACTION' in this repo (or any project) whenever you want to build/refresh its index."
  elif confirm "Run 'codegraph $CG_ACTION' for this repo now?"; then
    spin "Running codegraph $CG_ACTION..." codegraph "$CG_ACTION"
    ok "codegraph $CG_ACTION complete"
  else
    skip "Skipped - run 'codegraph $CG_ACTION' in this repo anytime"
  fi
else
  warn "codegraph install failed - skipping registration"
fi

step "browser-use (self-hosted, Claude-driven browser control)"
export BROWSER_USE_READY=false
# Kept as an array so browser-use[cli] is never glob-expanded on the way in.
BU_INSTALL=(uvx --python 3.12 "browser-use[cli]" install)
if [ "$HAS_UVX" != true ]; then
  skip "uvx not available"
elif [ -t 0 ] && confirm "Install browser-use's Chromium now? Runs '${BU_INSTALL[*]}', which may prompt for your sudo password."; then
  # Run directly, not through spin(): the underlying "playwright install
  # --with-deps" shells out to sudo apt-get on Linux, and a spinner would
  # hide that password prompt and hang the whole script silently.
  if "${BU_INSTALL[@]}"; then
    ok "browser-use Chromium installed"
    BROWSER_USE_READY=true
  else
    warn "Chromium install failed - run '${BU_INSTALL[*]}' manually later"
  fi
else
  ok "Will register - see the one-time Chromium install noted below"
fi

step "librarian-mcp (Obsidian)"
if install_tool librarian-mcp https://github.com/ngmeyer/librarian-mcp/releases/latest/download/librarian-mcp-installer.sh; then
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
OS_NAME="$(uname -s)"
if [ "$OS_NAME" != Linux ] && [ "$OS_NAME" != Darwin ]; then
  skip "Not supported on $OS_NAME without WSL (lightpanda has no native Windows build yet)"
elif [ "${SKIP_LIGHTPANDA:-}" = "1" ]; then
  skip "SKIP_LIGHTPANDA=1"
elif install_tool lightpanda https://pkg.lightpanda.io/install.sh; then
  ok "lightpanda installed"
  HAS_LIGHTPANDA=true
else
  warn "lightpanda install failed - lightpanda MCP entry will be skipped"
fi

step "CLAUDE.md for this repo"
PROMPT_FILE="$REPO_ROOT/CLAUDE_TEMPLATE.md"
COPY_LEAD="Copy this into any Claude Code session (here or another project) whenever you want to generate a CLAUDE.md:"
show_prompt() {
  echo "  $1"
  if [ -n "$GUM" ]; then
    "$GUM" format <"$PROMPT_FILE"
  else
    echo "  ----------------------------------------------------------------"
    cat "$PROMPT_FILE"
    echo "  ----------------------------------------------------------------"
  fi
}
if [ -f "$REPO_ROOT/CLAUDE.md" ]; then
  skip "CLAUDE.md already exists - not touching it"
elif [ ! -t 0 ]; then
  show_prompt "Not an interactive terminal - here's the prompt, paste it into any Claude Code session when you're ready:"
elif ! confirm "Initialize CLAUDE.md for this repo now with Claude Code?"; then
  show_prompt "$COPY_LEAD"
elif ! command -v claude >/dev/null; then
  warn "claude CLI not found on PATH - here's the prompt instead"
  show_prompt "$COPY_LEAD"
else
  # --allowedTools "Edit(CLAUDE.md)" scopes write access to just this one
  # file, so claude -p can actually create it instead of stopping to ask
  # for permission (which, in a non-interactive -p run, it can't get - it
  # would otherwise print a conversational "may I write this?" and never
  # create the file). Output is captured, not streamed, and only shown if
  # CLAUDE.md doesn't actually exist afterward.
  CLAUDE_MD_LOG="$(mktemp)"
  claude -p "$(cat "$PROMPT_FILE")" --allowedTools "Edit(CLAUDE.md)" >"$CLAUDE_MD_LOG" 2>&1
  if [ -f "$REPO_ROOT/CLAUDE.md" ]; then
    ok "CLAUDE.md generated - review it"
  else
    warn "claude -p didn't create CLAUDE.md - see below, or use the prompt instead"
    cat "$CLAUDE_MD_LOG"
    show_prompt "$COPY_LEAD"
  fi
  rm -f "$CLAUDE_MD_LOG"
fi

step "Registering MCP servers into ~/.claude.json"
python3 "$REPO_ROOT/scripts/merge-mcp-config.py"

step "Firecrawl (self-hosted web scraping)"
if [ "$HAS_DOCKER" != true ]; then
  skip "docker unavailable"
elif [ "${SKIP_FIRECRAWL:-}" = "1" ]; then
  skip "SKIP_FIRECRAWL=1"
else
  spin "Bringing up self-hosted Firecrawl..." bash "$REPO_ROOT/scripts/setup-firecrawl.sh" ||
    warn "Firecrawl bring-up failed - see output above"
fi

step "Bifrost gateway"
if [ "${SKIP_BIFROST:-}" = "1" ]; then
  skip "SKIP_BIFROST=1"
elif curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://localhost:8080 2>/dev/null | grep -q 200; then
  ok "Already running on http://localhost:8080"
else
  nohup npx -y @maximhq/bifrost >/tmp/bifrost.log 2>&1 &
  disown
  ok "Starting in background (log: /tmp/bifrost.log) - give it a few seconds"
fi

step "Summary - what's left for you"
# Blue - a plain to-do list, distinct from the warnings/issues below.
block 4 34 "1. Open http://localhost:8080, finish Bifrost onboarding, generate a virtual key.
   claude mcp add --transport http bifrost http://localhost:8080/mcp --header \"Authorization: Bearer <key>\" --scope user
2. In the Bifrost UI, add downstream servers you'd rather gateway than run direct
   (command/args/env are in mcp/mcp-servers.json).

Run scripts/verify-env.sh anytime to recheck what's installed."

# Warnings (yellow): not configured yet, but not wrong - just incomplete.
# Issues (red): actively misconfigured - something was set, but it's wrong.
WARNINGS=()
ISSUES=()
[ -n "${GITHUB_TOKEN:-}${GITHUB_PERSONAL_ACCESS_TOKEN:-}" ] ||
  WARNINGS+=("- Set GITHUB_TOKEN and re-run to register the GitHub MCP server.")
if [ "$HAS_UVX" != true ]; then
  WARNINGS+=("- Install uv/uvx (https://docs.astral.sh/uv/) and re-run to enable the browser-use MCP server.")
elif [ "$BROWSER_USE_READY" != true ]; then
  WARNINGS+=("- Run '${BU_INSTALL[*]}' once before first using the browser-use MCP (installs Chromium, may prompt for sudo on Linux).")
fi
if [ -z "${OBSIDIAN_VAULT_PATH:-}" ]; then
  WARNINGS+=("- Set OBSIDIAN_VAULT_PATH and re-run to register the Obsidian (librarian-mcp) server.")
elif [ ! -d "$OBSIDIAN_VAULT_PATH" ]; then
  ISSUES+=("- OBSIDIAN_VAULT_PATH ($OBSIDIAN_VAULT_PATH) is not an existing directory - fix it and re-run to register the Obsidian (librarian-mcp) server.")
fi

if [ ${#ISSUES[@]} -gt 0 ] || [ ${#WARNINGS[@]} -gt 0 ]; then
  step "Warnings & issues"
  if [ ${#ISSUES[@]} -gt 0 ]; then block 1 31 "$(printf '%s\n' "${ISSUES[@]}")"; fi
  if [ ${#WARNINGS[@]} -gt 0 ]; then block 3 33 "$(printf '%s\n' "${WARNINGS[@]}")"; fi
fi
