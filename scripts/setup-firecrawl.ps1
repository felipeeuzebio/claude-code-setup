#!/usr/bin/env pwsh
# Windows counterpart to setup-firecrawl.sh - brings up self-hosted Firecrawl
# via Docker Compose. Requires Docker Desktop.
$ErrorActionPreference = "Stop"

$CheckoutDir = if ($env:FIRECRAWL_CHECKOUT_DIR) { $env:FIRECRAWL_CHECKOUT_DIR } else { Join-Path $HOME "services\firecrawl" }
$RepoUrl = "https://github.com/firecrawl/firecrawl.git"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "docker not found on PATH. Install/start Docker Desktop first."
    exit 1
}

if (-not (Test-Path $CheckoutDir)) {
    git clone --depth 1 $RepoUrl $CheckoutDir
} else {
    git -C $CheckoutDir pull --ff-only
}

$envTarget = Join-Path $CheckoutDir ".env"
if (-not (Test-Path $envTarget)) {
    Copy-Item (Join-Path $ScriptDir "..\.env.example") $envTarget
}

Write-Host "Starting Firecrawl via docker compose in $CheckoutDir ..."
Push-Location $CheckoutDir
try {
    docker compose up -d
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Firecrawl should be reachable at http://localhost:3002"
