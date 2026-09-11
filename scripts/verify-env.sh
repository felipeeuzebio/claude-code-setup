#!/usr/bin/env bash
# Quick check of what this setup depends on being present.
set -uo pipefail

check() {
  local name="$1" cmd="$2"
  if command -v "$cmd" &>/dev/null; then
    printf '  ok   %-12s %s\n' "$name" "$("$cmd" --version 2>&1 | head -1)"
  elif type "$cmd" &>/dev/null; then
    printf '  ok   %-12s (shell function/alias only - no standalone binary)\n' "$name"
  else
    printf '  MISS %-12s not found on PATH\n' "$name"
  fi
}

echo "Runtime:"
check node node
check npx npx
check uvx uvx
check docker docker

echo
echo "Optional (setup.sh downloads a temporary copy if missing):"
check gum gum

echo
echo "Search / graph:"
check ripgrep rg
check codegraph codegraph

echo
echo "Browser engine:"
check lightpanda lightpanda

echo
echo "GitHub CLI:"
check gh gh
gh auth status 2>&1 | sed 's/^/  /'
