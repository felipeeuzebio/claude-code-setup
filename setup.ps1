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

# Every styled line goes through Write-Line or Write-Block. With gum: a
# colored glyph. Without: the same text behind a word label. $gumColor is a
# gum 256-color code, $hostColor its Write-Host equivalent for the fallback.
function Write-Line($gumColor, $hostColor, $glyph, $label, $msg) {
    if ($Gum) { "  $glyph $msg" | & $Gum style --foreground $gumColor }
    else { Write-Host "  $label $msg" -ForegroundColor $hostColor }
}
function Write-Block($gumColor, $hostColor, $text) {
    if ($Gum) { $text | & $Gum style --foreground $gumColor }
    else { Write-Host $text -ForegroundColor $hostColor }
}
function Ok($msg) { Write-Line 2 Green "+" "ok  " $msg }
function Skip($msg) { Write-Line 8 DarkGray "-" "skip" $msg }
function Warn($msg) { Write-Line 3 Yellow "!" "warn" $msg }
function Step($msg) {
    Write-Host ""
    if ($Gum) { "==> $msg" | & $Gum style --foreground 212 } else { Write-Host "==> $msg" -ForegroundColor Cyan }
}
# Like Ok, but prints the version dimmed so the tool name stands out. Color
# needs forcing here: capturing gum's output into a variable hands it a pipe
# instead of the real console, so its own TTY check would otherwise decide
# color is unsupported and print plain text for both halves.
function OkVer($label, $ver) {
    if (-not $Gum) { Write-Host "  ok   $label $ver" -ForegroundColor Green; return }
    $prevForce = $env:CLICOLOR_FORCE
    $env:CLICOLOR_FORCE = if ([Console]::IsOutputRedirected) { "" } else { "1" }
    $head = "  + $label " | & $Gum style --foreground 2
    $tail = "$ver" | & $Gum style --foreground 8
    $env:CLICOLOR_FORCE = $prevForce
    Write-Host "$head$tail"
}
# gum's TUI runs the console in raw mode, so Ctrl+C there is a keystroke
# gum interprets itself (exit 130), not a signal that would stop this
# script - so every gum confirm/spin call is checked for it explicitly.
function Stop-Setup {
    Write-Block 1 Red "Setup cancelled."
    exit 130
}
# Runs $exe with $exeArgs, showing a spinner; output only surfaces on failure.
# --spinner line: plain ASCII (-\|/), not gum's default Braille-dot frames,
# which render as mangled boxes in terminals/fonts without that Unicode block.
function Invoke-Spin($title, $exe, [string[]]$exeArgs) {
    if (-not $Gum) { Write-Host "  ... $title"; & $exe @exeArgs; return }
    & $Gum spin --spinner line --title $title --show-error -- $exe @exeArgs
    if ($LASTEXITCODE -eq 130) { Stop-Setup }
}
# Asks a y/n question; returns $true for yes, $false for no.
function Confirm-Gum($prompt) {
    if (-not $Gum) { return ((Read-Host "  $prompt [y/N]") -match '^[Yy]$') }
    & $Gum confirm $prompt
    if ($LASTEXITCODE -eq 130) { Stop-Setup }
    return ($LASTEXITCODE -eq 0)
}
function Test-Tool($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }
# Installs $name via the PowerShell one-liner installer at $url unless it's
# already on PATH. Deliberately returns nothing - callers re-check with
# Test-Tool instead. A return value here would swallow the installer's (and
# the spinner's) console output into the pipeline, and routing that to
# Out-Host to compensate would hand gum a non-tty stdout, which stops the
# spinner from rendering at all.
function Install-Tool($name, $url) {
    if (Test-Tool $name) { return }
    Invoke-Spin "Installing $name..." "pwsh" @("-NoProfile", "-Command", "irm $url | iex")
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
if (Test-Tool git) {
    git -C $RepoRoot rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -eq 0) {
        git -C $RepoRoot config core.hooksPath githooks
        Ok "commit-msg now enforces Conventional Commits (see githooks/commit-msg)"
    } else {
        Skip "Not a git checkout"
    }
} else {
    Skip "git not available"
}

Step "Checking required tools"
if (-not (Test-Tool node)) {
    Warn "node is required - install it first (https://nodejs.org)"
    exit 1
}
$python = @("python3", "python") | Where-Object { Test-Tool $_ } | Select-Object -First 1
if (-not $python) {
    Warn "python3 is required - it runs scripts\merge-mcp-config.py (https://python.org)"
    exit 1
}
OkVer "node" (node --version)
OkVer "npx" (npx --version)
OkVer $python (& $python --version)

$hasDocker = $false
if (Test-Tool docker) {
    try { docker info | Out-Null; $hasDocker = $true; OkVer "docker" (docker --version) }
    catch { Warn "docker found but not running - start Docker Desktop" }
} else {
    Warn "docker not available - Firecrawl self-host will be skipped"
}

$env:HAS_UVX = "false"
if (Test-Tool uvx) {
    $env:HAS_UVX = "true"
    OkVer "uvx" (uvx --version)
} else {
    Warn "uvx not available - browser-use (self-hosted) will be skipped (install: https://docs.astral.sh/uv/)"
}

Step "Codegraph"
Install-Tool codegraph "https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.ps1"
if (Test-Tool codegraph) {
    # codegraph's own installer prints a multi-line status box (its own
    # terminal UI, not ours) - the spinner hides it and only surfaces it on failure.
    Invoke-Spin "Registering codegraph in Claude Code..." "codegraph" @("install", "--target", "claude", "--location", "global", "-y")
    Ok "codegraph registered in Claude Code"

    # init builds an index from scratch, sync refreshes the existing one.
    $cgAction = if (Test-Path (Join-Path $RepoRoot ".codegraph")) { "sync" } else { "init" }
    if ([Console]::IsInputRedirected) {
        Write-Host "  Run 'codegraph $cgAction' in this repo (or any project) whenever you want to build/refresh its index."
    } elseif (Confirm-Gum "Run 'codegraph $cgAction' for this repo now?") {
        Invoke-Spin "Running codegraph $cgAction..." "codegraph" @($cgAction)
        Ok "codegraph $cgAction complete"
    } else {
        Skip "Skipped - run 'codegraph $cgAction' in this repo anytime"
    }
} else {
    Warn "codegraph install failed - skipping registration"
}

Step "browser-use (self-hosted, Claude-driven browser control)"
$env:BROWSER_USE_READY = "false"
$buInstall = "uvx --python 3.12 browser-use[cli] install"
if ($env:HAS_UVX -ne "true") {
    Skip "uvx not available"
} elseif (-not [Console]::IsInputRedirected -and (Confirm-Gum "Install browser-use's Chromium now? Runs '$buInstall'.")) {
    & uvx --python 3.12 browser-use[cli] install
    if ($LASTEXITCODE -eq 0) {
        Ok "browser-use Chromium installed"
        $env:BROWSER_USE_READY = "true"
    } else {
        Warn "Chromium install failed - run '$buInstall' manually later"
    }
} else {
    Ok "Will register - see the one-time Chromium install noted below"
}

Step "librarian-mcp (Obsidian)"
Install-Tool librarian-mcp "https://github.com/ngmeyer/librarian-mcp/releases/latest/download/librarian-mcp-installer.ps1"
if (Test-Tool librarian-mcp) {
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
$env:HAS_LIGHTPANDA = "false"
Skip "No native Windows build yet - run setup.sh under WSL2 for this piece"

Step "CLAUDE.md for this repo"
$promptFile = Join-Path $RepoRoot "CLAUDE_TEMPLATE.md"
$claudeMdPath = Join-Path $RepoRoot "CLAUDE.md"
$copyLead = "Copy this into any Claude Code session (here or another project) whenever you want to generate a CLAUDE.md:"
if (Test-Path $claudeMdPath) {
    Skip "CLAUDE.md already exists - not touching it"
} elseif ([Console]::IsInputRedirected) {
    Show-Prompt "Not an interactive terminal - here's the prompt, paste it into any Claude Code session when you're ready:" $promptFile
} elseif (-not (Confirm-Gum "Initialize CLAUDE.md for this repo now with Claude Code?")) {
    Show-Prompt $copyLead $promptFile
} elseif (-not (Test-Tool claude)) {
    Warn "claude CLI not found on PATH - here's the prompt instead"
    Show-Prompt $copyLead $promptFile
} else {
    # --allowedTools "Edit(CLAUDE.md)" scopes write access to just this
    # file, so claude -p can actually create it instead of stopping to ask
    # for permission it can't get non-interactively. Output is captured,
    # not streamed, and only shown if the file wasn't created.
    $claudeMdLog = New-TemporaryFile
    claude -p (Get-Content $promptFile -Raw) --allowedTools "Edit(CLAUDE.md)" *> $claudeMdLog
    if (Test-Path $claudeMdPath) {
        Ok "CLAUDE.md generated - review it"
    } else {
        Warn "claude -p didn't create CLAUDE.md - see below, or use the prompt instead"
        Get-Content $claudeMdLog
        Show-Prompt $copyLead $promptFile
    }
    Remove-Item $claudeMdLog -ErrorAction SilentlyContinue
}

Step "Registering MCP servers into ~/.claude.json"
& $python (Join-Path $RepoRoot "scripts\merge-mcp-config.py")

Step "Firecrawl (self-hosted web scraping)"
if (-not $hasDocker) {
    Skip "docker unavailable"
} elseif ($env:SKIP_FIRECRAWL -eq "1") {
    Skip "SKIP_FIRECRAWL=1"
} else {
    Invoke-Spin "Bringing up self-hosted Firecrawl..." "pwsh" @("-NoProfile", "-File", (Join-Path $RepoRoot "scripts\setup-firecrawl.ps1"))
}

Step "Bifrost gateway"
if ($env:SKIP_BIFROST -eq "1") {
    Skip "SKIP_BIFROST=1"
} else {
    $running = $false
    try { $running = (Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch {}
    if ($running) {
        Ok "Already running on http://localhost:8080"
    } else {
        Start-Process -FilePath "npx" -ArgumentList "-y", "@maximhq/bifrost" -WindowStyle Hidden
        Ok "Starting in background - give it a few seconds, then open http://localhost:8080"
    }
}

Step "Summary - what's left for you"
# Blue - a plain to-do list, distinct from the warnings/issues below.
Write-Block 4 Blue (@(
    "1. Open http://localhost:8080, finish Bifrost onboarding, generate a virtual key.",
    "   claude mcp add --transport http bifrost http://localhost:8080/mcp --header `"Authorization: Bearer <key>`" --scope user",
    "2. In the Bifrost UI, add downstream servers you'd rather gateway than run direct",
    "   (command/args/env are in mcp/mcp-servers.json).",
    "",
    "Run scripts\verify-env.ps1 anytime to recheck what's installed."
) -join "`n")

# Warnings (yellow): not configured yet, but not wrong - just incomplete.
# Issues (red): actively misconfigured - something was set, but it's wrong.
$warnings = @()
$issues = @()
if (-not ($env:GITHUB_TOKEN -or $env:GITHUB_PERSONAL_ACCESS_TOKEN)) {
    $warnings += "- Set GITHUB_TOKEN and re-run to register the GitHub MCP server."
}
if ($env:HAS_UVX -ne "true") {
    $warnings += "- Install uv/uvx (https://docs.astral.sh/uv/) and re-run to enable the browser-use MCP server."
} elseif ($env:BROWSER_USE_READY -ne "true") {
    $warnings += "- Run '$buInstall' once before first using the browser-use MCP (installs Chromium)."
}
if (-not $env:OBSIDIAN_VAULT_PATH) {
    $warnings += "- Set OBSIDIAN_VAULT_PATH and re-run to register the Obsidian (librarian-mcp) server."
} elseif (-not (Test-Path -LiteralPath $env:OBSIDIAN_VAULT_PATH -PathType Container)) {
    $issues += "- OBSIDIAN_VAULT_PATH ($($env:OBSIDIAN_VAULT_PATH)) is not an existing directory - fix it and re-run to register the Obsidian (librarian-mcp) server."
}

if ($issues.Count -gt 0 -or $warnings.Count -gt 0) {
    Step "Warnings & issues"
    if ($issues.Count -gt 0) { Write-Block 1 Red ($issues -join "`n") }
    if ($warnings.Count -gt 0) { Write-Block 3 Yellow ($warnings -join "`n") }
}

} finally {
    if ($GumTmpDir) { Remove-Item -Recurse -Force $GumTmpDir -ErrorAction SilentlyContinue }
}
