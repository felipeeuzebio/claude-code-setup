"""Merges the MCP servers this repo manages into ~/.claude.json, skipping
any server whose required tool isn't available rather than writing a
broken entry. Setup handles no secrets: GitHub (the one server that needs a
token) is registered by the user, and setup only prints the command.

Internal-only: called from setup's main() during a normal run. There's no
standalone re-merge command any more - re-run `./setup.sh` (it's
idempotent) instead.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import time
from pathlib import Path
from typing import Callable

from rich.markup import escape

from claude_code_setup.core import ui
from claude_code_setup.mcp.servers import load_managed_servers

Server = dict
Fill = Callable[[Server], Server]
Rule = tuple[bool, Fill, str]

# Not merged here - absence from build_plan() is intentional, not a missing
# rule. codegraph registers itself via its own installer; github needs a
# personal access token, which the user adds themselves (github_add_command).
UNMANAGED = {"codegraph", "github"}
GITHUB_PAT_PLACEHOLDER = "<your-PAT>"


def _env_flag(name: str, env: dict[str, str]) -> bool:
    return bool(re.match(r"^(1|true)$", env.get(name, ""), re.IGNORECASE))


def build_plan(env: dict[str, str]) -> dict[str, Rule]:
    has_lightpanda = _env_flag("HAS_LIGHTPANDA", env)
    has_uvx = _env_flag("HAS_UVX", env)

    return {
        "context7": (True, lambda s: s, ""),
        "dbx": (True, lambda s: s, ""),
        "browser-use": (has_uvx, lambda s: s, "uvx not on PATH"),
        "lightpanda": (
            has_lightpanda,
            lambda s: s,
            "lightpanda not installed or not supported on this OS",
        ),
        # codegraph and github are in UNMANAGED above - no entry needed here.
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


def github_add_command() -> str:
    """The `claude mcp add` line for the GitHub server as defined in
    mcp-servers.json, with a placeholder where the user's PAT goes."""
    server = load_managed_servers()["github"]
    env_flags = [f"-e {key}={GITHUB_PAT_PLACEHOLDER}" for key in server.get("env", {})]
    command = shlex.join([server["command"], *server.get("args", [])])
    return " ".join(["claude mcp add github --scope user", *env_flags, "--", command])


def is_registered(name: str, env: dict[str, str] | None = None) -> bool:
    """Whether ~/.claude.json already has an MCP server called `name`."""
    path = _resolve_target_path(dict(os.environ) if env is None else env)
    if not path.exists():
        return False
    return name in _load_json(path).get("mcpServers", {})


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
