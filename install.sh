#!/usr/bin/env bash
# One-line bootstrap for Linux/WSL2/macOS - no git clone needed:
#
#   curl -fsSL https://raw.githubusercontent.com/felipeeuzebio/claude-code-setup/main/install.sh | bash
#
# Run it from the project whose CLAUDE.md you want generated. Downloads this
# repo into a temporary directory (installing uv first if it's missing),
# runs its setup.sh against the dir you ran this from, then deletes the
# download - nothing of this repo stays on disk. Just the CLAUDE.md step:
#
#   curl -fsSL .../install.sh | bash -s -- --claude-md-only
#
# Optional env var:
#   CLAUDE_CODE_SETUP_REF  branch or tag to download (default: main)
#
# Everything lives inside main() so a truncated download never runs half a script.
set -euo pipefail

# Global, not local: the EXIT trap runs after main() has returned.
WORKDIR=""

cleanup() {
  if [ -n "$WORKDIR" ]; then rm -rf "$WORKDIR"; fi
}

main() {
  local repo="felipeeuzebio/claude-code-setup"
  local ref="${CLAUDE_CODE_SETUP_REF:-main}"

  # The caller's dir is the project; remember it before cd-ing anywhere.
  export CLAUDE_CODE_SETUP_PROJECT_DIR="${CLAUDE_CODE_SETUP_PROJECT_DIR:-$PWD}"

  for cmd in curl tar; do
    command -v "$cmd" >/dev/null || { echo "$cmd is required" >&2; exit 1; }
  done

  # uv stays installed: the browser-use MCP server setup registers runs on uvx.
  if ! command -v uv >/dev/null; then
    echo "==> Installing uv (https://docs.astral.sh/uv/)"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  fi

  WORKDIR="$(mktemp -d)"
  trap cleanup EXIT  # also on failure and Ctrl+C
  echo "==> Downloading $repo@$ref into a temporary directory"
  curl -fsSL "https://github.com/$repo/archive/$ref.tar.gz" \
    | tar -xz -C "$WORKDIR" --strip-components=1
  cd "$WORKDIR"

  # Under `curl | bash` stdin is the script pipe, so setup would see no TTY
  # and skip every y/n prompt - hand it the terminal back when there is one.
  if (exec </dev/tty) 2>/dev/null; then
    ./setup.sh "$@" </dev/tty
  else
    ./setup.sh "$@"
  fi
}

main "$@"
