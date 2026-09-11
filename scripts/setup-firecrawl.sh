#!/usr/bin/env bash
# Bring up a self-hosted Firecrawl instance via Docker Compose.
# Requires Docker (Docker Desktop WSL integration enabled, or Docker Engine
# installed natively) - see ../docs/DECISIONS.md.
set -euo pipefail

CHECKOUT_DIR="${FIRECRAWL_CHECKOUT_DIR:-$HOME/services/firecrawl}"
REPO_URL="https://github.com/firecrawl/firecrawl.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v docker &>/dev/null; then
  echo "docker not found on PATH." >&2
  echo "If you're on WSL2 with Docker Desktop: enable Settings > Resources > WSL Integration for this distro, then restart your shell." >&2
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
