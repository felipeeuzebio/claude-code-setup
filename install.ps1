# One-line bootstrap for native Windows - no git clone needed:
#
#   irm https://raw.githubusercontent.com/felipeeuzebio/claude-code-setup/main/install.ps1 | iex
#
# Run it from the project whose CLAUDE.md you want generated. Downloads this
# repo's zip into ~\.claude-code-setup (installing uv first if it's missing),
# then runs its setup.ps1 against the dir you ran this from. Re-running it
# updates that copy in place, keeping its .env and .codegraph\.
#
# Optional env vars:
#   CLAUDE_CODE_SETUP_DIR  install location (default: ~\.claude-code-setup)
#   CLAUDE_CODE_SETUP_REF  branch or tag to download (default: main)
# plus anything setup.ps1 reads (GITHUB_TOKEN, SKIP_BIFROST=1, ...).
#
# Wrapped in a function so a truncated download never runs half a script,
# and so nothing leaks into the caller's session under `iex`.

function Install-ClaudeCodeSetup {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'  # Invoke-WebRequest is far slower with the progress bar

    $Repo = 'felipeeuzebio/claude-code-setup'
    $Ref = if ($env:CLAUDE_CODE_SETUP_REF) { $env:CLAUDE_CODE_SETUP_REF } else { 'main' }
    $Dest = if ($env:CLAUDE_CODE_SETUP_DIR) { $env:CLAUDE_CODE_SETUP_DIR } else { Join-Path $HOME '.claude-code-setup' }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host '==> Installing uv (https://docs.astral.sh/uv/)'
        powershell -NoProfile -ExecutionPolicy ByPass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
        $env:Path = "$(Join-Path $HOME '.local\bin');$env:Path"
    }

    # A real git checkout is the user's to update - just run it as-is.
    if (Test-Path (Join-Path $Dest '.git')) {
        Write-Host "==> $Dest is a git checkout - leaving it alone (git pull to update)"
    } else {
        Write-Host "==> Downloading $Repo@$Ref into $Dest"
        $Tmp = Join-Path ([IO.Path]::GetTempPath()) ([IO.Path]::GetRandomFileName())
        New-Item -ItemType Directory -Path $Tmp | Out-Null
        try {
            $Zip = Join-Path $Tmp 'src.zip'
            Invoke-WebRequest "https://github.com/$Repo/archive/$Ref.zip" -OutFile $Zip -UseBasicParsing
            Expand-Archive $Zip -DestinationPath $Tmp
            # GitHub zips hold a single top-level <repo>-<ref> folder.
            $Src = (Get-ChildItem $Tmp -Directory | Select-Object -First 1).FullName

            # Local-only state that isn't in the zip survives the update.
            foreach ($Keep in '.env', '.codegraph') {
                $Old = Join-Path $Dest $Keep
                if (Test-Path $Old) { Move-Item $Old (Join-Path $Src $Keep) }
            }
            if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force }
            New-Item -ItemType Directory -Path (Split-Path $Dest -Parent) -Force | Out-Null
            Move-Item $Src $Dest
        } finally {
            Remove-Item $Tmp -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    if (-not (Test-Path (Join-Path $Dest '.env'))) {
        Write-Host "==> Tip: copy $Dest\.env.example to $Dest\.env to add secrets, then re-run"
    }

    # The caller's dir is the project. Passed as an env var, not the child's
    # cwd: Windows PowerShell 5.1 doesn't sync Set-Location to the process cwd.
    $HadProjectDir = [bool]$env:CLAUDE_CODE_SETUP_PROJECT_DIR
    if (-not $HadProjectDir) { $env:CLAUDE_CODE_SETUP_PROJECT_DIR = (Get-Location).Path }
    try {
        # Run in its own process so setup.ps1's `exit` doesn't close the caller's window under `iex`.
        $Shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
        & $Shell -NoProfile -ExecutionPolicy ByPass -File (Join-Path $Dest 'setup.ps1')
    } finally {
        if (-not $HadProjectDir) { Remove-Item Env:CLAUDE_CODE_SETUP_PROJECT_DIR -ErrorAction SilentlyContinue }
    }
}

Install-ClaudeCodeSetup
