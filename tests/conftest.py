"""Shared fixtures + custom CLI options for the MCP integration suite
(test_mcp_servers.py). Session-scoped so prerequisites (a headless Chrome,
the registered-server lookup) are set up once per pytest run, not once per
case - matching test-mcp.py's original PREREQS caching-per-key behavior.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import cast

import pytest

from setup.mcpservers import REPO_ROOT, load_managed_servers

CLAUDE_CONFIG = Path.home() / ".claude.json"
CHROME_PORT = 9223


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--model", default="sonnet", help="model alias to test with (default: sonnet)"
    )
    parser.addoption(
        "--mcp-timeout",
        type=int,
        default=300,
        help="per-case timeout in seconds for the MCP suite (default: 300)",
    )


@pytest.fixture(scope="session")
def model(request: pytest.FixtureRequest) -> str:
    return cast(str, request.config.getoption("--model"))


@pytest.fixture(scope="session")
def mcp_timeout(request: pytest.FixtureRequest) -> int:
    return cast(int, request.config.getoption("--mcp-timeout"))


@pytest.fixture(scope="session")
def registered_servers() -> dict:
    """Best-effort read of ~/.claude.json's mcpServers - missing file or
    unparseable JSON is treated as empty, same as test-mcp.py's
    load_registered()."""
    if not CLAUDE_CONFIG.exists():
        return {}
    try:
        return json.loads(CLAUDE_CONFIG.read_text(encoding="utf-8")).get("mcpServers", {}) or {}
    except (json.JSONDecodeError, OSError):
        return {}


@pytest.fixture(scope="session")
def managed_servers() -> dict:
    return load_managed_servers()


def _cdp_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
            return bool(json.loads(r.read()).get("webSocketDebuggerUrl"))
    except OSError:
        return False


def _find_chromium() -> str | None:
    for pattern in ("chromium-*/chrome-linux*/chrome", "chromium-*/chrome-*/Chromium"):
        hits = sorted((Path.home() / ".cache" / "ms-playwright").glob(pattern))
        if hits:
            return str(hits[-1])
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _wait_for(port: int, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _cdp_alive(port):
            return True
        time.sleep(0.4)
    return False


@pytest.fixture(scope="session")
def chrome_prereq():
    """Starts a headless Chromium on CHROME_PORT if one isn't already up;
    only kills what this fixture itself started. Skips (once, cached for
    the whole session) if no Chromium-family browser can be found."""
    if _cdp_alive(CHROME_PORT):
        yield
        return

    exe = _find_chromium()
    if not exe:
        pytest.skip(
            "no Chromium-family browser found (run: uvx --python 3.12 'browser-use[cli]' install)"
        )

    profile = tempfile.mkdtemp(prefix="mcp-test-chrome-")
    proc = subprocess.Popen(
        [
            exe,
            "--headless=new",
            f"--remote-debugging-port={CHROME_PORT}",
            "--no-sandbox",
            "--disable-gpu",
            f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_for(CHROME_PORT):
            proc.terminate()
            pytest.skip("Chromium did not expose a CDP port")
        yield
    finally:
        proc.terminate()


@pytest.fixture(scope="session")
def codegraph_index():
    if not (REPO_ROOT / ".codegraph").is_dir():
        pytest.skip("no .codegraph index here (run: codegraph init)")
