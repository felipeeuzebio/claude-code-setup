"""`.env` parsing - no shell semantics, ever.

Deliberately not evaluated as shell: an unquoted value containing a space
or backslash (e.g. a Windows-style OBSIDIAN_VAULT_PATH) must survive
byte-for-byte. Strips exactly one matching layer of "..."/'...' quotes
from the value and nothing else - no expansion, no escaping.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_BLANK_OR_COMMENT = re.compile(r"^\s*(#.*)?$")


def load_env(path: Path) -> dict[str, str]:
    """Parses a .env file into a dict. Missing file -> empty dict."""
    if not path.is_file():
        return {}

    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\r")
        if _BLANK_OR_COMMENT.match(line):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = re.sub(r"\s+", "", key)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        result[key] = value
    return result


def apply_env(env_vars: dict[str, str]) -> None:
    """Exports parsed .env values into the process environment."""
    os.environ.update(env_vars)
