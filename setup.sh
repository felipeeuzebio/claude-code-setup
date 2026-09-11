#!/usr/bin/env bash
# One-shot setup for this Claude Code environment on Linux/macOS/WSL2.
# Installs what it can, registers what it can into ~/.claude.json, and
# prints exactly what's left for you to do by hand (secrets, Bifrost UI).
#
# Optional config via env vars or a repo-root .env file (see .env.example):
#   GITHUB_TOKEN, BROWSER_USE_API_KEY, OBSIDIAN_VAULT_PATH,
#   SKIP_FIRECRAWL=1, SKIP_BIFROST=1, SKIP_LIGHTPANDA=1
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
ok()   { printf '  ok   %s\n' "$1"; }
skip() { printf '  skip %s\n' "$1"; }
warn() { printf '  warn %s\n' "$1" >&2; }

step "Checking required tools"
command -v node >/dev/null || { echo "node is required - install it first (https://nodejs.org)"; exit 1; }
command -v npx  >/dev/null || { echo "npx is required (ships with node >=8.2)"; exit 1; }
ok "node $(node --version), npx $(npx --version)"

HAS_DOCKER=false
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  HAS_DOCKER=true
  ok "docker $(docker --version | cut -d, -f1)"
else
  warn "docker not available - Firecrawl self-host will be skipped (see docs/DECISIONS.md)"
fi

OS_NAME="$(uname -s)"
CAN_USE_LIGHTPANDA=false
[ "$OS_NAME" = "Linux" ] || [ "$OS_NAME" = "Darwin" ] && CAN_USE_LIGHTPANDA=true

step "Codegraph"
if ! command -v codegraph >/dev/null; then
  curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
if command -v codegraph >/dev/null; then
  codegraph install --target claude --location global -y
  ok "codegraph $(codegraph version 2>/dev/null || echo installed) registered in Claude Code"
else
  warn "codegraph install failed - skipping registration"
fi

step "librarian-mcp (Obsidian)"
if ! command -v librarian-mcp >/dev/null; then
  curl -fsSL "https://github.com/ngmeyer/librarian-mcp/releases/latest/download/librarian-mcp-installer.sh" | sh
  export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
fi
if command -v librarian-mcp >/dev/null; then
  ok "librarian-mcp installed"
  [ -n "${OBSIDIAN_VAULT_PATH:-}" ] || warn "OBSIDIAN_VAULT_PATH not set - obsidian MCP entry will be skipped"
else
  warn "librarian-mcp install failed - obsidian MCP entry will be skipped"
fi

step "Lightpanda (fast local browser engine)"
export HAS_LIGHTPANDA=false
if [ "$CAN_USE_LIGHTPANDA" = true ] && [ "${SKIP_LIGHTPANDA:-}" != "1" ]; then
  if ! command -v lightpanda >/dev/null; then
    curl -fsSL https://pkg.lightpanda.io/install.sh | bash
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

step "Installing /init-claude-md slash command"
mkdir -p "$HOME/.claude/commands"
cp "$REPO_ROOT/claude-md/init-claude-md.md" "$HOME/.claude/commands/init-claude-md.md"
ok "run /init-claude-md in any project to generate its CLAUDE.md from the standard template"

step "Registering MCP servers into ~/.claude.json"
node "$REPO_ROOT/scripts/merge-mcp-config.js"

step "Firecrawl (self-hosted web scraping)"
if [ "$HAS_DOCKER" = true ] && [ "${SKIP_FIRECRAWL:-}" != "1" ]; then
  bash "$REPO_ROOT/scripts/setup-firecrawl.sh" || warn "Firecrawl bring-up failed - see output above"
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
echo "  1. Open http://localhost:8080, finish Bifrost onboarding, generate a virtual key."
echo "     claude mcp add --transport http bifrost http://localhost:8080/mcp --header \"Authorization: Bearer <key>\" --scope user"
echo "  2. In the Bifrost UI, add downstream servers you'd rather gateway than run direct"
echo "     (command/args/env are in mcp/mcp-servers.json)."
[ -n "${GITHUB_TOKEN:-}${GITHUB_PERSONAL_ACCESS_TOKEN:-}" ] || echo "  - Set GITHUB_TOKEN and re-run to register the GitHub MCP server."
[ -n "${BROWSER_USE_API_KEY:-}" ] || echo "  - Set BROWSER_USE_API_KEY and re-run to register the browser-use MCP server."
[ -n "${OBSIDIAN_VAULT_PATH:-}" ] || echo "  - Set OBSIDIAN_VAULT_PATH and re-run to register the Obsidian (librarian-mcp) server."
echo "  Run scripts/verify-env.sh anytime to recheck what's installed."
