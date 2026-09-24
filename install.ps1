# One-line bootstrap for native Windows - no git clone needed:
#
#   irm https://raw.githubusercontent.com/felipeeuzebio/claude-code-setup/main/install.ps1 | iex
#
# Run it from the project whose CLAUDE.md you want generated. Downloads this
# repo's zip into a temporary directory (installing uv first if it's
# missing), runs its setup.ps1 against the dir you ran this from, then
# deletes the download - nothing of this repo stays on disk.
#
# Optional env var:
#   CLAUDE_CODE_SETUP_REF  branch or tag to download (default: main)
#
# Wrapped in a function so a truncated download never runs half a script,
# and so nothing leaks into the caller's session under `iex`.

function Install-ClaudeCodeSetup {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'  # Invoke-WebRequest is far slower with the progress bar

    $Repo = 'felipeeuzebio/claude-code-setup'
    $Ref = if ($env:CLAUDE_CODE_SETUP_REF) { $env:CLAUDE_CODE_SETUP_REF } else { 'main' }

    # uv stays installed: the browser-use MCP server setup registers runs on uvx.
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host '==> Installing uv (https://docs.astral.sh/uv/)'
        powershell -NoProfile -ExecutionPolicy ByPass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
        $env:Path = "$(Join-Path $HOME '.local\bin');$env:Path"
    }

    $Work = Join-Path ([IO.Path]::GetTempPath()) ([IO.Path]::GetRandomFileName())
    New-Item -ItemType Directory -Path $Work | Out-Null

    # The caller's dir is the project. Passed as an env var, not the child's
    # cwd: Windows PowerShell 5.1 doesn't sync Set-Location to the process cwd.
    $HadProjectDir = [bool]$env:CLAUDE_CODE_SETUP_PROJECT_DIR
    if (-not $HadProjectDir) { $env:CLAUDE_CODE_SETUP_PROJECT_DIR = (Get-Location).Path }
    try {
        Write-Host "==> Downloading $Repo@$Ref into a temporary directory"
        $Zip = Join-Path $Work 'src.zip'
        Invoke-WebRequest "https://github.com/$Repo/archive/$Ref.zip" -OutFile $Zip -UseBasicParsing
        Expand-Archive $Zip -DestinationPath $Work
        # GitHub zips hold a single top-level <repo>-<ref> folder.
        $Src = (Get-ChildItem $Work -Directory | Select-Object -First 1).FullName

        # Run in its own process so setup.ps1's `exit` doesn't close the caller's window under `iex`.
        $Shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
        & $Shell -NoProfile -ExecutionPolicy ByPass -File (Join-Path $Src 'setup.ps1')
    } finally {
        # Also on failure and Ctrl+C: the download never outlives the run.
        Remove-Item $Work -Recurse -Force -ErrorAction SilentlyContinue
        if (-not $HadProjectDir) { Remove-Item Env:CLAUDE_CODE_SETUP_PROJECT_DIR -ErrorAction SilentlyContinue }
    }
}

Install-ClaudeCodeSetup
