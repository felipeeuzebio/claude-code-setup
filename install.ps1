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

    $Work = Join-Path ([IO.Path]::GetTempPath()) ([IO.Path]::GetRandomFileName())
    New-Item -ItemType Directory -Path $Work | Out-Null

    # The caller's dir is the project. Passed as an env var, not the child's
    # cwd: Windows PowerShell 5.1 doesn't sync Set-Location to the process cwd.
    $HadProjectDir = [bool]$env:CLAUDE_CODE_SETUP_PROJECT_DIR
    if (-not $HadProjectDir) { $env:CLAUDE_CODE_SETUP_PROJECT_DIR = (Get-Location).Path }
    $Job = $null
    try {
        # Everything before setup's own UI runs in a background job behind a
        # spinner, its output hidden: install uv if missing (it stays - the
        # browser-use MCP server runs on uvx), download the repo, and build its
        # virtualenv so `uv run` in setup.ps1 has nothing left to print.
        $Job = Start-Job -ArgumentList $Repo, $Ref, $Work -ScriptBlock {
            param($Repo, $Ref, $Work)
            # Not 'Stop' job-wide: in Windows PowerShell 5.1 that turns any stderr
            # line from a native command (uv) into an error, even on success.
            # Cmdlets get -ErrorAction Stop, native commands their exit code.
            $ProgressPreference = 'SilentlyContinue'
            $env:Path = "$(Join-Path $HOME '.local\bin');$env:Path"
            if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
                $Out = powershell -NoProfile -ExecutionPolicy ByPass -Command 'irm https://astral.sh/uv/install.ps1 | iex' 2>&1
                if ($LASTEXITCODE -ne 0) { throw "Installing uv failed:`n$($Out -join "`n")" }
            }
            $Zip = Join-Path $Work 'src.zip'
            Invoke-WebRequest "https://github.com/$Repo/archive/$Ref.zip" -OutFile $Zip -UseBasicParsing -ErrorAction Stop
            Expand-Archive $Zip -DestinationPath $Work -ErrorAction Stop
            # GitHub zips hold a single top-level <repo>-<ref> folder.
            $Src = (Get-ChildItem $Work -Directory | Select-Object -First 1).FullName
            Push-Location $Src
            try { $Out = & uv sync --quiet 2>&1 } finally { Pop-Location }
            if ($LASTEXITCODE -ne 0) { throw "uv sync failed:`n$($Out -join "`n")" }
        }
        $Frames = '-', '\', '|', '/'
        $i = 0
        while ($Job.State -in 'NotStarted', 'Running') {
            Write-Host -NoNewline "`r$($Frames[$i++ % 4]) Initializing Claude Code Setup"
            Start-Sleep -Milliseconds 100
        }
        Write-Host -NoNewline "`r$(' ' * 40)`r"
        Receive-Job $Job -ErrorAction Stop | Out-Null  # rethrows whatever failed in the job

        $env:Path = "$(Join-Path $HOME '.local\bin');$env:Path"
        $Src = (Get-ChildItem $Work -Directory | Select-Object -First 1).FullName

        # Run in its own process so setup.ps1's `exit` doesn't close the caller's window under `iex`.
        $Shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
        & $Shell -NoProfile -ExecutionPolicy ByPass -File (Join-Path $Src 'setup.ps1')
    } finally {
        # Also on failure and Ctrl+C: the download never outlives the run.
        if ($Job) { Remove-Job $Job -Force -ErrorAction SilentlyContinue }
        Remove-Item $Work -Recurse -Force -ErrorAction SilentlyContinue
        if (-not $HadProjectDir) { Remove-Item Env:CLAUDE_CODE_SETUP_PROJECT_DIR -ErrorAction SilentlyContinue }
    }
}

Install-ClaudeCodeSetup
