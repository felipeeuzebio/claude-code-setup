#!/usr/bin/env bash
# One-line bootstrap for Linux/WSL2/macOS - no git clone needed:
#
#   curl -fsSL https://raw.githubusercontent.com/felipeeuzebio/claude-code-setup/main/install.sh | bash
#
# Run it from the project whose CLAUDE.md you want generated. Downloads this
# repo's tarball into ~/.claude-code-setup (installing uv first if it's
# missing), then runs its setup.sh against the dir you ran this from.
# Re-running it updates that copy in place, keeping its .env and .codegraph/.
# Just the CLAUDE.md step:
#
#   curl -fsSL .../install.sh | bash -s -- --claude-md-only
#
# Optional env vars:
#   CLAUDE_CODE_SETUP_DIR  install location (default: ~/.claude-code-setup)
#   CLAUDE_CODE_SETUP_REF  branch or tag to download (default: main)
# plus anything setup.sh reads (GITHUB_TOKEN, SKIP_BIFROST=1, ...).
#
# Everything lives inside main() so a truncated download never runs half a script.
set -euo pipefail

main() {
  local repo="felipeeuzebio/claude-code-setup"
  local ref="${CLAUDE_CODE_SETUP_REF:-main}"
  local dest="${CLAUDE_CODE_SETUP_DIR:-$HOME/.claude-code-setup}"

  # The caller's dir is the project; remember it before cd-ing anywhere.
  export CLAUDE_CODE_SETUP_PROJECT_DIR="${CLAUDE_CODE_SETUP_PROJECT_DIR:-$PWD}"

  for cmd in curl tar; do
    command -v "$cmd" >/dev/null || { echo "$cmd is required" >&2; exit 1; }
  done

  if ! command -v uv >/dev/null; then
    echo "==> Installing uv (https://docs.astral.sh/uv/)"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  fi

  # A real git checkout is the user's to update - just run it as-is.
  if [ -d "$dest/.git" ]; then
    echo "==> $dest is a git checkout - leaving it alone (git pull to update)"
  else
    echo "==> Downloading $repo@$ref into $dest"
    tmp="$(mktemp -d)"  # global: the EXIT trap runs after main returns
    trap 'rm -rf "$tmp"' EXIT
    mkdir "$tmp/src"
    curl -fsSL "https://github.com/$repo/archive/$ref.tar.gz" \
      | tar -xz -C "$tmp/src" --strip-components=1

    # Local-only state that isn't in the tarball survives the update.
    for keep in .env .codegraph; do
      if [ -e "$dest/$keep" ]; then mv "$dest/$keep" "$tmp/src/$keep"; fi
    done
    rm -rf "$dest"
    mkdir -p "$(dirname "$dest")"
    mv "$tmp/src" "$dest"
  fi

  cd "$dest"
  [ -f .env ] || echo "==> Tip: cp $dest/.env.example $dest/.env to add secrets, then re-run"

  # Under `curl | bash` stdin is the script pipe, so setup would see no TTY
  # and skip every y/n prompt - hand it the terminal back when there is one.
  if (exec </dev/tty) 2>/dev/null; then
    ./setup.sh "$@" </dev/tty
  else
    ./setup.sh "$@"
  fi
}

main "$@"
