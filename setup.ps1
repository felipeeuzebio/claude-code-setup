#!/usr/bin/env pwsh
# One-shot setup for this Claude Code environment - native Windows. This is
# a thin wrapper: all the actual logic lives in the `setup` Python package
# under src/, run via `uv`.
#
# Run it from the project whose CLAUDE.md you want generated; pass
# --claude-md-only to skip everything else.
# No config file: optional pieces are asked about as it runs.

# The caller's dir is the project; remember it before Set-Location.
if (-not $env:CLAUDE_CODE_SETUP_PROJECT_DIR) { $env:CLAUDE_CODE_SETUP_PROJECT_DIR = (Get-Location).Path }

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is required (https://docs.astral.sh/uv/) - it manages the Python interpreter and dependencies for this project; no separate Python install needed."
    exit 1
}

& uv run setup @args
exit $LASTEXITCODE
