#!/usr/bin/env pwsh
# One-shot setup for this Claude Code environment on native Windows.
# Installs what it can, registers what it can into ~/.claude.json, and
# prints exactly what's left for you to do by hand (secrets, Bifrost UI).
#
# Optional config via env vars or a repo-root .env file (see .env.example):
#   GITHUB_TOKEN, OBSIDIAN_VAULT_PATH,
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

# gum is cosmetic only - if it can't be found or downloaded, everything
# below falls back to plain output instead of failing the whole setup.
# Resolution is silent; nothing is printed either way.
. (Join-Path $RepoRoot "scripts\ensure-gum.ps1")

function Step($msg) {
    if ($Gum) { Write-Host ""; "==> $msg" | & $Gum style --foreground 212 }
    else { Write-Host "`n==> $msg" -ForegroundColor Cyan }
}
function Ok($msg)   { if ($Gum) { "  + $msg" | & $Gum style --foreground 2 } else { Write-Host "  ok   $msg" } }
function Skip($msg) { if ($Gum) { "  - $msg" | & $Gum style --foreground 8 } else { Write-Host "  skip $msg" } }
function Warn($msg) { if ($Gum) { "  ! $msg" | & $Gum style --foreground 3 } else { Write-Host "  warn $msg" -ForegroundColor Yellow } }
# gum's TUI runs the console in raw mode, so Ctrl+C there is a keystroke
# gum interprets itself (exit 130), not a signal that would stop this
# script - so every gum confirm/spin call is checked for it explicitly.
function Stop-Setup {
    if ($Gum) { "Setup cancelled." | & $Gum style --foreground 1 } else { Write-Host "Setup cancelled." }
    exit 130
}
# Runs $exe with $exeArgs, showing a spinner; output only surfaces on
# failure. Quits the whole setup (not just this step) if Ctrl+C was pressed.
# --spinner line: plain ASCII (-\|/), not gum's default Braille-dot frames,
# which render as mangled boxes in terminals/fonts without that Unicode block.
function Invoke-Spin($title, $exe, [string[]]$exeArgs) {
    if ($Gum) {
        & $Gum spin --spinner line --title $title --show-error -- $exe @exeArgs
        if ($LASTEXITCODE -eq 130) { Stop-Setup }
    } else { Write-Host "  ... $title"; & $exe @exeArgs }
}
function Confirm-Gum($prompt) {
    if ($Gum) {
        & $Gum confirm $prompt
        if ($LASTEXITCODE -eq 130) { Stop-Setup }
        return ($LASTEXITCODE -eq 0)
    } else { return ((Read-Host "  $prompt [y/N]") -match '^[Yy]$') }
}
function Show-Prompt($lead, $promptFile) {
    Write-Host "  $lead"
    if ($Gum) { Get-Content $promptFile -Raw | & $Gum format }
    else {
        Write-Host "  ----------------------------------------------------------------"
        Get-Content $promptFile | ForEach-Object { Write-Host "  $_" }
        Write-Host "  ----------------------------------------------------------------"
    }
}

try {

Step "Git commit-msg hook"
if (Get-Command git -ErrorAction SilentlyContinue) {
    git -C $RepoRoot rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -eq 0) {
        git -C $RepoRoot config core.hooksPath githooks
        Ok "commit-msg now enforces Conventional Commits (see githooks/commit-msg)"
    } else {
        Skip "not a git checkout"
    }
} else {
    Skip "git not available"
}

Step "Checking required tools"
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error "node is required - install it first (https://nodejs.org)"
    exit 1
}
$python = @("python3", "python") | Where-Object { Get-Command $_ -ErrorAction SilentlyContinue } | Select-Object -First 1
if (-not $python) {
    Write-Error "python3 is required for scripts\merge-mcp-config.py - install it first (https://python.org)"
    exit 1
}
Ok "node $(node --version), npx $(npx --version), $python $(& $python --version)"

$hasDocker = $false
if (Get-Command docker -ErrorAction SilentlyContinue) {
    try { docker info | Out-Null; $hasDocker = $true; Ok "docker $(docker --version)" }
    catch { Warn "docker found but not running - start Docker Desktop" }
} else {
    Warn "docker not available - Firecrawl self-host will be skipped"
}

$env:HAS_UVX = "false"
if (Get-Command uvx -ErrorAction SilentlyContinue) {
    $env:HAS_UVX = "true"
    Ok "uvx $(uvx --version)"
} else {
    Warn "uvx not available - browser-use (self-hosted) will be skipped (install: https://docs.astral.sh/uv/)"
}

Step "Codegraph"
if (-not (Get-Command codegraph -ErrorAction SilentlyContinue)) {
    Invoke-Spin "Installing codegraph..." "pwsh" @("-NoProfile", "-Command", "irm https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.ps1 | iex")
}
if (Get-Command codegraph -ErrorAction SilentlyContinue) {
    # codegraph's own installer prints a multi-line status box (its own
    # terminal UI, not ours) - the spinner hides it and only surfaces it on failure.
    Invoke-Spin "Registering codegraph in Claude Code..." "codegraph" @("install", "--target", "claude", "--location", "global", "-y")
    Ok "codegraph registered in Claude Code"

    $codegraphDir = Join-Path $RepoRoot ".codegraph"
    if (Test-Path $codegraphDir) {
        $cgAction = "sync"; $cgPrompt = "Sync codegraph's index for this repo now (codegraph sync)?"; $cgSkipMsg = "not synced"
    } else {
        $cgAction = "init"; $cgPrompt = "Index this repo with codegraph now (codegraph init)?"; $cgSkipMsg = "not indexed"
    }
    if ([Console]::IsInputRedirected) {
        Write-Host "  Run 'codegraph $cgAction' in this repo (or any project) whenever you want to build/refresh its index."
    } elseif (Confirm-Gum $cgPrompt) {
        Invoke-Spin "Running codegraph $cgAction..." "codegraph" @($cgAction)
        Ok "codegraph $cgAction complete"
    } else {
        Skip "$cgSkipMsg - run 'codegraph $cgAction' in this repo anytime"
    }
} else {
    Warn "codegraph install failed - skipping registration"
}

Step "Set up browser-use (self-hosted, Claude-driven browser control)"
if ($env:HAS_UVX -eq "true") {
    Ok "will register (see summary below for the one-time Chromium install)"
} else {
    Skip "uvx not available"
}

Step "librarian-mcp (Obsidian)"
if (-not (Get-Command librarian-mcp -ErrorAction SilentlyContinue)) {
    Invoke-Spin "Installing librarian-mcp..." "pwsh" @("-NoProfile", "-Command", "irm https://github.com/ngmeyer/librarian-mcp/releases/latest/download/librarian-mcp-installer.ps1 | iex")
}
if (Get-Command librarian-mcp -ErrorAction SilentlyContinue) {
    Ok "librarian-mcp installed"
    if (-not $env:OBSIDIAN_VAULT_PATH) {
        Warn "OBSIDIAN_VAULT_PATH not set - obsidian MCP entry will be skipped"
    } elseif (-not (Test-Path -LiteralPath $env:OBSIDIAN_VAULT_PATH -PathType Container)) {
        Warn "OBSIDIAN_VAULT_PATH is not an existing directory: $($env:OBSIDIAN_VAULT_PATH) - obsidian MCP entry will be skipped"
    }
} else {
    Warn "librarian-mcp install failed - obsidian MCP entry will be skipped"
}

Step "Lightpanda (fast local browser engine)"
Skip "no native Windows build yet - run setup.sh under WSL2 for this piece"
$env:HAS_LIGHTPANDA = "false"

Step "CLAUDE.md for this repo"
$promptFile = Join-Path $RepoRoot "claude-md\init-prompt.md"
$claudeMdPath = Join-Path $RepoRoot "CLAUDE.md"
if (Test-Path $claudeMdPath) {
    Skip "CLAUDE.md already exists - not touching it"
} elseif ([Console]::IsInputRedirected) {
    Show-Prompt "Not an interactive terminal - here's the prompt, paste it into any Claude Code session when you're ready:" $promptFile
} else {
    $confirmed = Confirm-Gum "Initialize CLAUDE.md for this repo now with Claude Code?"
    if ($confirmed -and (Get-Command claude -ErrorAction SilentlyContinue)) {
        claude -p (Get-Content $promptFile -Raw)
        Ok "CLAUDE.md generated - review it"
    } else {
        if ($confirmed) { Warn "claude CLI not found on PATH - here's the prompt instead" }
        Show-Prompt "Copy this into any Claude Code session (here or another project) whenever you want to generate a CLAUDE.md:" $promptFile
    }
}

Step "Registering MCP servers into ~/.claude.json"
& $python (Join-Path $RepoRoot "scripts\merge-mcp-config.py")

Step "Firecrawl (self-hosted web scraping)"
if ($hasDocker -and $env:SKIP_FIRECRAWL -ne "1") {
    Invoke-Spin "Bringing up self-hosted Firecrawl..." "pwsh" @("-NoProfile", "-File", (Join-Path $RepoRoot "scripts\setup-firecrawl.ps1"))
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
$summaryLines = @(
    "1. Open http://localhost:8080, finish Bifrost onboarding, generate a virtual key.",
    "   claude mcp add --transport http bifrost http://localhost:8080/mcp --header `"Authorization: Bearer <key>`" --scope user",
    "2. In the Bifrost UI, add downstream servers you'd rather gateway than run direct",
    "   (command/args/env are in mcp/mcp-servers.json)."
)
if (-not ($env:GITHUB_TOKEN -or $env:GITHUB_PERSONAL_ACCESS_TOKEN)) { $summaryLines += "- Set GITHUB_TOKEN and re-run to register the GitHub MCP server." }
if ($env:HAS_UVX -eq "true") {
    $summaryLines += "- Run 'uvx --python 3.12 browser-use[cli] install' once before first using the browser-use MCP (installs Chromium)."
} else {
    $summaryLines += "- Install uv/uvx (https://docs.astral.sh/uv/) and re-run to enable the browser-use MCP server."
}
if (-not $env:OBSIDIAN_VAULT_PATH) {
    $summaryLines += "- Set OBSIDIAN_VAULT_PATH and re-run to register the Obsidian (librarian-mcp) server."
} elseif (-not (Test-Path -LiteralPath $env:OBSIDIAN_VAULT_PATH -PathType Container)) {
    $summaryLines += "- OBSIDIAN_VAULT_PATH ($($env:OBSIDIAN_VAULT_PATH)) is not an existing directory - fix it and re-run to register the Obsidian (librarian-mcp) server."
}
$summaryLines += "Run scripts\verify-env.ps1 anytime to recheck what's installed."
$summary = $summaryLines -join "`n"

if ($Gum) { $summary | & $Gum style --foreground 212 }
else { Write-Host $summary }

} finally {
    if ($GumTmpDir) { Remove-Item -Recurse -Force $GumTmpDir -ErrorAction SilentlyContinue }
}
