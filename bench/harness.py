"""Shared runner for the benches: one `claude -p` session, locked to a given
set of MCP servers and tools, parsed into the numbers every bench records.

Same technique as tests/test_mcp_servers.py: --strict-mcp-config so only the
servers passed in exist, an allowlist of the arm's tools, a denylist of
everything that could answer without them, cwd in a scratch dir so no
project CLAUDE.md leaks in. "tool_bytes" (bytes returned by all tool
results) is the tokens-into-context proxy.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from setup.envfile import apply_env, load_env
from setup.mcpservers import REPO_ROOT

# Built-ins that could answer a bench prompt without the arm's tools. Benches
# that measure WebFetch/WebSearch themselves drop those two from the list.
DENIED_BUILTINS = "Bash,Read,Write,Edit,Glob,Grep,Task,NotebookEdit"
DENIED_WEB = "WebFetch,WebSearch"


def bench_env() -> dict[str, str]:
    """`.env` values the benches need, loaded the way `setup` loads them."""
    apply_env(load_env(REPO_ROOT / ".env"))
    return {
        "vault": os.environ.get("OBSIDIAN_VAULT_PATH", ""),
        "firecrawl_api_url": os.environ.get("FIRECRAWL_API_URL", "http://localhost:3002"),
    }


def run_session(
    prompt: str,
    servers: dict,
    allowed: list[str],
    *,
    denied: str,
    model: str,
    timeout: int,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="bench-") as tmp:
        config = Path(tmp) / "mcp.json"
        config.write_text(json.dumps({"mcpServers": servers}))
        cmd = [
            "claude", "-p", prompt,
            "--model", model,
            "--output-format", "stream-json", "--verbose",
            "--strict-mcp-config", "--mcp-config", str(config),
            "--allowedTools", ",".join(allowed),
            "--disallowedTools", denied,
        ]
        t0 = time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=tmp,
                                  stdin=subprocess.DEVNULL)
            stdout, timed_out = proc.stdout, False
        except subprocess.TimeoutExpired as exc:
            stdout, timed_out = (exc.stdout or b"").decode("utf-8", "replace"), True
        wall = time.time() - t0

    calls: list[str] = []
    offered: list[str] = []
    mcp_status: list = []
    tool_bytes = 0
    tool_errors = 0
    answer = ""
    usage: dict = {}
    duration_ms = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = ev.get("type")
        if kind == "system" and ev.get("subtype") == "init":
            offered = [t for t in ev.get("tools", []) if t.startswith("mcp__")]
            mcp_status = ev.get("mcp_servers") or []
        elif kind == "assistant":
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    calls.append(b.get("name", ""))
        elif kind == "user":
            for b in ev.get("message", {}).get("content", []) or []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    content = b.get("content")
                    if isinstance(content, list):
                        text = "".join(c.get("text", "") for c in content if isinstance(c, dict))
                    else:
                        text = str(content or "")
                    tool_bytes += len(text.encode("utf-8"))
                    if b.get("is_error"):
                        tool_errors += 1
        elif kind == "result":
            answer = str(ev.get("result") or "")
            usage = ev.get("usage") or {}
            duration_ms = ev.get("duration_ms")

    return {
        "calls": calls,
        "round_trips": len(calls),
        "tool_bytes": tool_bytes,
        "tool_tokens_est": tool_bytes // 4,
        "tool_errors": tool_errors,
        "mcp_status": mcp_status,
        "offered": len(offered),
        "usage": usage,
        "duration_ms": duration_ms,
        "wall_s": round(wall, 1),
        "timed_out": timed_out,
        "answer": answer[:1500],
    }
