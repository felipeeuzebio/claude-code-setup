"""Self-hosted Firecrawl bring-up via Docker Compose.

Internal-only: called from setup's own "Firecrawl" step, which has already
checked docker is ready and SKIP_FIRECRAWL before calling this - no
standalone "just bring up Firecrawl" command any more, re-run `./setup.sh`
instead (docker compose up -d is a no-op if it's already up).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from setup.mcpservers import REPO_ROOT

REPO_URL = "https://github.com/firecrawl/firecrawl.git"


@dataclass
class FirecrawlResult:
    ok: bool
    log: str = ""


def _default_checkout_dir() -> Path:
    override = os.environ.get("FIRECRAWL_CHECKOUT_DIR")
    return Path(override) if override else Path.home() / "services" / "firecrawl"


def bring_up(checkout_dir: Path | None = None) -> FirecrawlResult:
    """Clones/pulls the firecrawl repo, copies .env.example in
    non-destructively (never clobbers an edited checkout .env), and runs
    `docker compose up -d`."""
    checkout_dir = checkout_dir or _default_checkout_dir()
    log_parts: list[str] = []

    def run(*args: str, cwd: Path | None = None) -> bool:
        try:
            result = subprocess.run(
                args, cwd=cwd, capture_output=True, text=True, timeout=300
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log_parts.append(str(exc))
            return False
        if result.stdout:
            log_parts.append(result.stdout)
        if result.stderr:
            log_parts.append(result.stderr)
        return result.returncode == 0

    if not checkout_dir.is_dir():
        if not run("git", "clone", "--depth", "1", REPO_URL, str(checkout_dir)):
            return FirecrawlResult(False, "\n".join(log_parts))
    else:
        if not run("git", "-C", str(checkout_dir), "pull", "--ff-only"):
            return FirecrawlResult(False, "\n".join(log_parts))

    env_target = checkout_dir / ".env"
    if not env_target.exists():
        shutil.copyfile(REPO_ROOT / ".env.example", env_target)

    if not run("docker", "compose", "up", "-d", cwd=checkout_dir):
        return FirecrawlResult(False, "\n".join(log_parts))

    return FirecrawlResult(True, "\n".join(log_parts))
