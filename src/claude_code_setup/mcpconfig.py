"""Merges the MCP servers this repo manages into ~/.claude.json, skipping
any server whose required secret/path isn't available rather than writing
a broken entry.

Internal-only: called from setup's main() during a normal run. There's no
standalone re-merge command any more - after editing .env, re-run
`./setup.sh` (it's idempotent) instead.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Callable

from rich.markup import escape

from claude_code_setup import ui
from claude_code_setup.mcpservers import load_managed_servers

Server = dict
Fill = Callable[[Server], Server]
Rule = tuple[bool, Fill, str]

# Registered by their own installer, not merged here - absence from
# build_plan() is intentional, not a missing rule.
UNMANAGED = {"codegraph"}


def _env_flag(name: str, env: dict[str, str]) -> bool:
    return bool(re.match(r"^(1|true)$", env.get(name, ""), re.IGNORECASE))


def build_plan(env: dict[str, str]) -> dict[str, Rule]:
    github_token = env.get("GITHUB_TOKEN") or env.get("GITHUB_PERSONAL_ACCESS_TOKEN") or ""

    has_lightpanda = _env_flag("HAS_LIGHTPANDA", env)
    has_uvx = _env_flag("HAS_UVX", env)

    return {
        "context7": (True, lambda s: s, ""),
        "dbx": (True, lambda s: s, ""),
        "github": (
            bool(github_token),
            lambda s: {**s, "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": github_token}},
            "GITHUB_TOKEN (or GITHUB_PERSONAL_ACCESS_TOKEN) not set",
        ),
        "browser-use": (has_uvx, lambda s: s, "uvx not on PATH"),
        "lightpanda": (
            has_lightpanda,
            lambda s: s,
            "lightpanda not installed or not supported on this OS",
        ),
        # codegraph is in UNMANAGED above - no entry needed here.
    }


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _backup(path: Path) -> Path:
    backup_path = path.with_name(f"{path.name}.bak-{int(time.time() * 1000)}")
    backup_path.write_bytes(path.read_bytes())
    return backup_path


def _resolve_target_path(env: dict[str, str]) -> Path:
    # CLAUDE_HOME is a testability seam only - not used by real invocations.
    home = env.get("CLAUDE_HOME")
    base = Path(home) if home else Path.home()
    return base / ".claude.json"


def merge_and_write(
    env: dict[str, str] | None = None, target_path: Path | None = None
) -> list[str]:
    """Registers every ready MCP server (per build_plan) into ~/.claude.json,
    backing up any existing file first. Prints registered/skipped, same as
    the original merge-mcp-config.py, and returns the registered names."""
    if env is None:
        env = dict(os.environ)
    if target_path is None:
        target_path = _resolve_target_path(env)

    source = load_managed_servers()
    plan = build_plan(env)

    registered: list[str] = []
    skipped: list[tuple[str, str]] = []
    to_write: dict[str, Server] = {}

    for name, server in source.items():
        rule = plan.get(name)
        if rule is None:
            if name not in UNMANAGED:
                skipped.append((name, "no readiness rule in build_plan() - add one"))
            continue
        ready, fill, reason = rule
        if ready:
            to_write[name] = fill(server)
            registered.append(name)
        else:
            skipped.append((name, reason))

    target: dict = {"mcpServers": {}}
    if target_path.exists():
        target = _load_json(target_path)
        target.setdefault("mcpServers", {})
        ui.console.print(f"Backed up existing config to {escape(str(_backup(target_path)))}")

    target["mcpServers"] = {**target["mcpServers"], **to_write}
    target_path.write_text(json.dumps(target, indent=2) + "\n", encoding="utf-8")

    ui.console.print(
        f"Registered in {escape(str(target_path))}: {escape(', '.join(registered) or '(none)')}"
    )
    if skipped:
        ui.console.print("Skipped:")
        for name, reason in skipped:
            ui.console.print(f"  - {escape(name)}: {escape(reason)}", style="yellow")
    else:
        ui.console.print("Skipped: (none)")

    return registered
