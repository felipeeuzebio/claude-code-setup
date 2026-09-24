#!/usr/bin/env bash
# One-shot setup for this Claude Code environment - Linux/WSL2/macOS/native
# Windows alike. This is a thin wrapper: all the actual logic lives in the
# `setup` Python package under src/, run via `uv`.
#
# Run it from the project whose CLAUDE.md you want generated; pass
# --claude-md-only to skip everything else.
# No config file: optional pieces are asked about as it runs.
set -euo pipefail

# The caller's dir is the project; remember it before cd-ing into the repo.
export CLAUDE_CODE_SETUP_PROJECT_DIR="${CLAUDE_CODE_SETUP_PROJECT_DIR:-$PWD}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

command -v uv >/dev/null || {
  echo "uv is required (https://docs.astral.sh/uv/) - it manages the Python interpreter and dependencies for this project; no separate Python install needed." >&2
  exit 1
}

# --quiet: no "Installed N packages" chatter before setup's own UI.
exec uv run --quiet setup "$@"
