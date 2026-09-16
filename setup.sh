#!/usr/bin/env bash
# One-shot setup for this Claude Code environment - Linux/WSL2/macOS/native
# Windows alike. This is a thin wrapper: all the actual logic lives in the
# `setup` Python package under src/, run via `uv`.
#
# Optional config via env vars or a repo-root .env file (see .env.example):
#   GITHUB_TOKEN,
#   SKIP_BIFROST=1, SKIP_LIGHTPANDA=1
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

command -v uv >/dev/null || {
  echo "uv is required (https://docs.astral.sh/uv/) - it manages the Python interpreter and dependencies for this project; no separate Python install needed." >&2
  exit 1
}

exec uv run setup "$@"
