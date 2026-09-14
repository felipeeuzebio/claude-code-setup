"""Tool-detection helpers - consolidates what used to be three separate
ad hoc implementations (setup.sh's inline `command -v` checks, setup.ps1's
`Get-Command` checks, and verify-env.sh/.ps1's own `check()`/`Test-Cmd`)
into one shared, testable function.

Internal-only: there's no standalone "verify-env" report any more - the
tools this actually gates (node/npx/docker/uvx) are checked as part of
setup's own "Checking required tools" step, and re-running `./setup.sh`
(idempotent) is how you recheck what's installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess

# On Windows, npm-ecosystem tools (npx, and anything installed as a global
# npm package) commonly resolve to a `.CMD` shim - CreateProcess can't exec
# those directly (raises FileNotFoundError) without going through the
# shell. cmd/version_arg here are always trusted internal constants, never
# user input, so shell=True carries none of its usual injection risk.
_SHELL = os.name == "nt"


def check_tool(cmd: str, version_arg: str = "--version") -> tuple[bool, str]:
    """Returns (found, first line of version output) for `cmd` on PATH."""
    if not shutil.which(cmd):
        return False, ""
    try:
        result = subprocess.run(
            [cmd, version_arg], capture_output=True, text=True, timeout=10, shell=_SHELL
        )
    except (OSError, subprocess.TimeoutExpired):
        return True, ""
    text = (result.stdout or result.stderr).strip()
    return True, (text.splitlines()[0] if text else "")


def docker_ready() -> bool:
    """True if docker is on PATH AND the daemon is actually running."""
    if not shutil.which("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10, shell=_SHELL
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def docker_version() -> str:
    """Matches `docker --version | cut -d, -f1` - "Docker version X, build Y" -> "Docker version X"."""
    found, version = check_tool("docker")
    return version.split(",")[0] if found else ""
