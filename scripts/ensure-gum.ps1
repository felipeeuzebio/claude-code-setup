#!/usr/bin/env pwsh
# Dot-sourced by setup.ps1 (not executed directly). Sets:
#   $Gum       - path to a usable gum.exe, or $null if unavailable
#   $GumTmpDir - the throwaway dir gum was downloaded into, or $null if an
#                existing system install was used (nothing to clean up)
# Never installs gum system-wide - a temp download is the only "install"
# this does, and the caller is expected to remove $GumTmpDir on exit.
$Gum = $null
$GumTmpDir = $null

$existing = Get-Command gum -ErrorAction SilentlyContinue
if ($existing) {
    $Gum = $existing.Source
} else {
    try {
        $arch = if ([Environment]::Is64BitOperatingSystem) { "x86_64" } else { "i386" }
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/charmbracelet/gum/releases/latest" -UseBasicParsing
        $tag = $release.tag_name
        $version = $tag.TrimStart("v")
        $url = "https://github.com/charmbracelet/gum/releases/download/$tag/gum_${version}_Windows_$arch.zip"

        $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("gum-" + [System.Guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $tmp | Out-Null
        $zipPath = Join-Path $tmp "gum.zip"
        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $tmp -Force

        $exe = Get-ChildItem -Path $tmp -Filter "gum.exe" -Recurse | Select-Object -First 1
        if ($exe) {
            $Gum = $exe.FullName
            $GumTmpDir = $tmp
        } else {
            Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
        }
    } catch {
        $Gum = $null
        if ($GumTmpDir) { Remove-Item -Recurse -Force $GumTmpDir -ErrorAction SilentlyContinue }
        $GumTmpDir = $null
    }
}
