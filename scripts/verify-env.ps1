#!/usr/bin/env pwsh
# Windows counterpart to verify-env.sh - quick check of what this setup depends on.

function Test-Cmd {
    param([string]$Name, [string]$Cmd, [string]$VersionArg = "--version")
    $found = Get-Command $Cmd -ErrorAction SilentlyContinue
    if ($found) {
        $version = & $Cmd $VersionArg 2>&1 | Select-Object -First 1
        Write-Host ("  ok   {0,-14} {1}" -f $Name, $version)
    } else {
        Write-Host ("  MISS {0,-14} not found on PATH" -f $Name)
    }
}

Write-Host "Runtime:"
Test-Cmd "node" "node"
Test-Cmd "npx" "npx"
Test-Cmd "docker" "docker"

Write-Host ""
Write-Host "Search / graph:"
Test-Cmd "codegraph" "codegraph"

Write-Host ""
Write-Host "Browser engine:"
Write-Host "  --   lightpanda     no native Windows build - use WSL for this piece"

Write-Host ""
Write-Host "Obsidian:"
Test-Cmd "librarian-mcp" "librarian-mcp"

Write-Host ""
Write-Host "GitHub CLI:"
Test-Cmd "gh" "gh"
if (Get-Command gh -ErrorAction SilentlyContinue) {
    gh auth status 2>&1 | ForEach-Object { "  $_" }
}
