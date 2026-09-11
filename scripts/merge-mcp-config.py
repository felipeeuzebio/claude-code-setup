#!/usr/bin/env python3
"""Merges the MCP servers this repo manages into ~/.claude.json, skipping any
server whose required secret/path isn't available rather than writing a
broken entry. Shared by setup.sh and setup.ps1 so the merge logic - and its
bugs - only exist in one place.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = REPO_ROOT / "mcp" / "mcp-servers.json"
TARGET_PATH = Path.home() / ".claude.json"

Server = dict
Fill = Callable[[Server], Server]


def env_flag(name: str) -> bool:
    return bool(re.match(r"^(1|true)$", os.environ.get(name, ""), re.IGNORECASE))


def build_plan(env: dict) -> dict[str, tuple[bool, Fill]]:
    github_token = env.get("GITHUB_TOKEN") or env.get("GITHUB_PERSONAL_ACCESS_TOKEN") or ""
    openai_key = env.get("OPENAI_API_KEY", "")
    browser_use_model = env.get("BROWSER_USE_LLM_MODEL", "")
    vault_path = env.get("OBSIDIAN_VAULT_PATH", "")
    firecrawl_url = env.get("FIRECRAWL_API_URL", "http://localhost:3002")
    skip_firecrawl = env_flag("SKIP_FIRECRAWL")
    has_lightpanda = env_flag("HAS_LIGHTPANDA")
    has_uvx = env_flag("HAS_UVX")

    return {
        "context7": (True, lambda s: s),
        "github": (
            bool(github_token),
            lambda s: {**s, "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": github_token}},
        ),
        "firecrawl": (
            not skip_firecrawl,
            lambda s: {**s, "env": {**s.get("env", {}), "FIRECRAWL_API_URL": firecrawl_url}},
        ),
        "obsidian": (
            bool(vault_path),
            lambda s: {**s, "args": [vault_path]},
        ),
        "browser-use": (
            bool(openai_key) and has_uvx,
            lambda s: {
                **s,
                "env": {
                    **s.get("env", {}),
                    "OPENAI_API_KEY": openai_key,
                    **({"BROWSER_USE_LLM_MODEL": browser_use_model} if browser_use_model else {}),
                },
            },
        ),
        "lightpanda-playwright": (has_lightpanda, lambda s: s),
    }


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def backup(path: Path) -> Path:
    backup_path = path.with_name(f"{path.name}.bak-{int(time.time() * 1000)}")
    backup_path.write_bytes(path.read_bytes())
    return backup_path


def main() -> None:
    source = load_json(SOURCE_PATH)["mcpServers"]
    plan = build_plan(dict(os.environ))

    registered: list[str] = []
    skipped: list[str] = []
    to_write: dict[str, Server] = {}

    for name, server in source.items():
        rule = plan.get(name)
        if rule is None:
            continue  # codegraph is registered by its own installer, not here
        ready, fill = rule
        if ready:
            to_write[name] = fill(server)
            registered.append(name)
        else:
            skipped.append(name)

    target: dict = {"mcpServers": {}}
    if TARGET_PATH.exists():
        target = load_json(TARGET_PATH)
        target.setdefault("mcpServers", {})
        print(f"Backed up existing config to {backup(TARGET_PATH)}")

    target["mcpServers"] = {**target["mcpServers"], **to_write}
    TARGET_PATH.write_text(json.dumps(target, indent=2) + "\n", encoding="utf-8")

    print(f"Registered in {TARGET_PATH}: {', '.join(registered) or '(none)'}")
    print(f"Skipped (missing secret/dependency): {', '.join(skipped) or '(none)'}")


if __name__ == "__main__":
    main()
