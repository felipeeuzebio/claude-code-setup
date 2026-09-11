#!/usr/bin/env bash
# Bring up a self-hosted Firecrawl instance via Docker Compose.
# Requires Docker: native Docker Engine on Linux, Docker Desktop on macOS,
# or Docker Desktop with WSL integration enabled if running under WSL2 -
# see ../docs/DECISIONS.md.
set -euo pipefail

CHECKOUT_DIR="${FIRECRAWL_CHECKOUT_DIR:-$HOME/services/firecrawl}"
REPO_URL="https://github.com/firecrawl/firecrawl.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v docker &>/dev/null; then
  echo "docker not found on PATH." >&2
  if grep -qi microsoft /proc/version 2>/dev/null; then
    echo "You're on WSL2: if Docker Desktop is installed on the Windows side, enable Settings > Resources > WSL Integration for this distro, then restart your shell." >&2
  else
    echo "Install Docker Engine for your distro (https://docs.docker.com/engine/install/) or Docker Desktop, then make sure the docker daemon is running." >&2
  fi
  exit 1
fi

if [ ! -d "$CHECKOUT_DIR" ]; then
  git clone --depth 1 "$REPO_URL" "$CHECKOUT_DIR"
else
  git -C "$CHECKOUT_DIR" pull --ff-only
fi

cp -n "$SCRIPT_DIR/../firecrawl/.env.example" "$CHECKOUT_DIR/.env" || true

echo "Starting Firecrawl via docker compose in $CHECKOUT_DIR ..."
(cd "$CHECKOUT_DIR" && docker compose up -d)

echo
echo "Firecrawl should be reachable at http://localhost:3002"
echo "Point mcp/mcp-servers.json's firecrawl.env.FIRECRAWL_API_URL at that address (already set by default)."
