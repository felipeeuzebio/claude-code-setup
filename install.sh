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

REPO="felipeeuzebio/claude-code-setup"
SPINNER_TEXT="Initializing Claude Code Setup"

# Globals, not locals: the EXIT trap runs after main() has returned.
WORKDIR=""
SPINNER_PID=""

cleanup() {
  # Ctrl+C mid-spinner: the background job ignores SIGINT (no job control),
  # so stop it here, and give the cursor back.
  if [ -n "$SPINNER_PID" ]; then kill "$SPINNER_PID" 2>/dev/null || true; fi
  if [ -t 2 ]; then printf '\033[?25h' >&2; fi
  if [ -n "$WORKDIR" ]; then rm -rf "$WORKDIR"; fi
}

# Everything before setup's own UI: install uv if missing, download the repo,
# and build its virtualenv so `uv run` in setup.sh has nothing left to print.
# Every step checks itself: with_spinner calls this in a `||` list, where
# `set -e` is switched off.
prepare() {
  local ref="$1"
  if ! command -v uv >/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh || return
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  fi
  curl -fsSL "https://github.com/$REPO/archive/$ref.tar.gz" \
    | tar -xz -C "$WORKDIR" --strip-components=1 || return
  (cd "$WORKDIR" && uv sync --quiet) || return
}

# Runs "$@" with its output hidden behind a one-line spinner on stderr; if it
# fails, prints what it said and fails too. A plain line when not a terminal.
with_spinner() {
  local log="$WORKDIR/.install.log" status=0  # inside WORKDIR: cleanup() takes it too
  if [ ! -t 2 ]; then
    echo "$SPINNER_TEXT..." >&2
    "$@" </dev/null >"$log" 2>&1 || status=$?
  else
    "$@" </dev/null >"$log" 2>&1 &
    SPINNER_PID=$!
    local frames='-\|/' i=0
    printf '\033[?25l' >&2
    while kill -0 "$SPINNER_PID" 2>/dev/null; do
      printf '\r%s %s' "${frames:i++%4:1}" "$SPINNER_TEXT" >&2
      sleep 0.1
    done
    wait "$SPINNER_PID" || status=$?
    SPINNER_PID=""
    printf '\r\033[K\033[?25h' >&2
  fi
  if [ "$status" -ne 0 ]; then cat "$log" >&2; fi
  rm -f "$log"
  return "$status"
}

main() {
  local ref="${CLAUDE_CODE_SETUP_REF:-main}"

  # The caller's dir is the project; remember it before cd-ing anywhere.
  export CLAUDE_CODE_SETUP_PROJECT_DIR="${CLAUDE_CODE_SETUP_PROJECT_DIR:-$PWD}"

  for cmd in curl tar; do
    command -v "$cmd" >/dev/null || { echo "$cmd is required" >&2; exit 1; }
  done

  WORKDIR="$(mktemp -d)"
  trap cleanup EXIT  # also on failure and Ctrl+C
  with_spinner prepare "$ref"
  # prepare ran in a subshell; uv stays installed (browser-use runs on uvx)
  # but its PATH update didn't make it back here.
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
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
