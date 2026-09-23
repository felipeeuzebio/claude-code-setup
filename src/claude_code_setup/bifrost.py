"""Bifrost gateway health-check + background start.

Internal-only, called from setup's own "Bifrost gateway" step.
"""

from __future__ import annotations

import subprocess
import sys
import urllib.request
from pathlib import Path

URL = "http://localhost:8080"


def is_running() -> bool:
    try:
        with urllib.request.urlopen(URL, timeout=2) as resp:
            return resp.status == 200
    except OSError:
        return False


def start_background(log_path: Path) -> None:
    """Starts `npx -y @maximhq/bifrost` detached, logging to log_path -
    matches `nohup npx ... & disown`."""
    with open(log_path, "ab") as log_file:
        popen_kwargs: dict = {
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            # npx resolves to a .CMD shim on Windows - needs the shell to
            # exec it - plus CREATE_NO_WINDOW so no console flashes up.
            popen_kwargs["shell"] = True
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            popen_kwargs["start_new_session"] = True
        subprocess.Popen(["npx", "-y", "@maximhq/bifrost"], **popen_kwargs)
