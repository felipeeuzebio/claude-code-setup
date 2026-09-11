#!/usr/bin/env pwsh
# One-shot setup for this Claude Code environment on native Windows.
# Installs what it can, registers what it can into ~/.claude.json, and
# prints exactly what's left for you to do by hand (secrets, Bifrost UI).
#
# Optional config via env vars or a repo-root .env file (see .env.example):
#   GITHUB_TOKEN, BROWSER_USE_API_KEY, OBSIDIAN_VAULT_PATH,
#   SKIP_FIRECRAWL=1, SKIP_BIFROST=1
#
# Note: Lightpanda has no native Windows build yet - that piece only runs
# under WSL2. Use setup.sh inside WSL for the full stack including it.

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$envFile = Join-Path $RepoRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match '^\s*[^#][^=]*=' } | ForEach-Object {
        $key, $value = $_.Split('=', 2)
        [Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process")
    }
}

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  ok   $msg" }
function Skip($msg) { Write-Host "  skip $msg" }
function Warn($msg) { Write-Host "  warn $msg" -ForegroundColor Yellow }

Step "Checking required tools"
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error "node is required - install it first (https://nodejs.org)"
    exit 1
}
Ok "node $(node --version), npx $(npx --version)"

$hasDocker = $false
if (Get-Command docker -ErrorAction SilentlyContinue) {
    try { docker info | Out-Null; $hasDocker = $true; Ok "docker $(docker --version)" }
    catch { Warn "docker found but not running - start Docker Desktop" }
} else {
    Warn "docker not available - Firecrawl self-host will be skipped"
}

Step "Codegraph"
if (-not (Get-Command codegraph -ErrorAction SilentlyContinue)) {
    irm https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.ps1 | iex
}
if (Get-Command codegraph -ErrorAction SilentlyContinue) {
    codegraph install --target claude --location global -y
    Ok "codegraph registered in Claude Code"
} else {
    Warn "codegraph install failed - skipping registration"
}

Step "librarian-mcp (Obsidian)"
if (-not (Get-Command librarian-mcp -ErrorAction SilentlyContinue)) {
    irm "https://github.com/ngmeyer/librarian-mcp/releases/latest/download/librarian-mcp-installer.ps1" | iex
}
if (Get-Command librarian-mcp -ErrorAction SilentlyContinue) {
    Ok "librarian-mcp installed"
    if (-not $env:OBSIDIAN_VAULT_PATH) { Warn "OBSIDIAN_VAULT_PATH not set - obsidian MCP entry will be skipped" }
} else {
    Warn "librarian-mcp install failed - obsidian MCP entry will be skipped"
}

Step "Lightpanda (fast local browser engine)"
Skip "no native Windows build yet - run setup.sh under WSL2 for this piece"
$env:HAS_LIGHTPANDA = "false"

Step "Registering MCP servers into ~/.claude.json"
node (Join-Path $RepoRoot "scripts\merge-mcp-config.js")

Step "Firecrawl (self-hosted web scraping)"
if ($hasDocker -and $env:SKIP_FIRECRAWL -ne "1") {
    & (Join-Path $RepoRoot "scripts\setup-firecrawl.ps1")
} else {
    Skip "docker unavailable or SKIP_FIRECRAWL=1"
}

Step "Bifrost gateway"
if ($env:SKIP_BIFROST -ne "1") {
    $running = $false
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $running = $true }
    } catch {}
    if ($running) {
        Ok "already running on http://localhost:8080"
    } else {
        Start-Process -FilePath "npx" -ArgumentList "-y", "@maximhq/bifrost" -WindowStyle Hidden
        Ok "starting in background - give it a few seconds, then open http://localhost:8080"
    }
} else {
    Skip "SKIP_BIFROST=1"
}

Step "Summary - what's left for you"
Write-Host "  1. Open http://localhost:8080, finish Bifrost onboarding, generate a virtual key."
Write-Host "     claude mcp add --transport http bifrost http://localhost:8080/mcp --header `"Authorization: Bearer <key>`" --scope user"
Write-Host "  2. In the Bifrost UI, add downstream servers you'd rather gateway than run direct"
Write-Host "     (command/args/env are in mcp/mcp-servers.json)."
if (-not ($env:GITHUB_TOKEN -or $env:GITHUB_PERSONAL_ACCESS_TOKEN)) { Write-Host "  - Set GITHUB_TOKEN and re-run to register the GitHub MCP server." }
if (-not $env:BROWSER_USE_API_KEY) { Write-Host "  - Set BROWSER_USE_API_KEY and re-run to register the browser-use MCP server." }
if (-not $env:OBSIDIAN_VAULT_PATH) { Write-Host "  - Set OBSIDIAN_VAULT_PATH and re-run to register the Obsidian (librarian-mcp) server." }
Write-Host "  Run scripts\verify-env.ps1 anytime to recheck what's installed."
