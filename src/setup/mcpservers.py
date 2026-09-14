"""Shared loader for mcp-servers.json - the source-of-truth MCP server list.

Used by both mcpconfig.py (merging ready servers into ~/.claude.json) and
tests/test_mcp_servers.py (checking which servers this repo manages).
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_PATH = REPO_ROOT / "mcp-servers.json"


def load_managed_servers(path: Path = SOURCE_PATH) -> dict[str, dict]:
    """Returns the `mcpServers` mapping from mcp-servers.json."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["mcpServers"]
