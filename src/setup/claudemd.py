"""CLAUDE.md-generation step: offers to run `claude -p` against
CLAUDE_TEMPLATE.md, falling back to showing the prompt for manual use.

Internal-only, called from setup's own "CLAUDE.md for this repo" step.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from rich.markup import escape

from setup import ui
from setup.mcpservers import REPO_ROOT

PROMPT_FILE = REPO_ROOT / "CLAUDE_TEMPLATE.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
COPY_LEAD = (
    "Copy this into any Claude Code session (here or another project) "
    "whenever you want to generate a CLAUDE.md:"
)


def _show_prompt(lead: str) -> None:
    ui.console.print(f"  {lead}")
    # Restores gum format's Markdown rendering, dropped nowhere else in
    # this rewrite - `rich` covers it directly.
    ui.render_markdown(PROMPT_FILE.read_text(encoding="utf-8"))


def ensure_claude_md() -> None:
    if CLAUDE_MD.exists():
        ui.skip("CLAUDE.md already exists - not touching it")
        return

    if not sys.stdin.isatty():
        _show_prompt(
            "Not an interactive terminal - here's the prompt, paste it into "
            "any Claude Code session when you're ready:"
        )
        return

    if not ui.confirm("Initialize CLAUDE.md for this repo now with Claude Code?"):
        _show_prompt(COPY_LEAD)
        return

    if not shutil.which("claude"):
        ui.warn("claude CLI not found on PATH - here's the prompt instead")
        _show_prompt(COPY_LEAD)
        return

    prompt_text = PROMPT_FILE.read_text(encoding="utf-8")
    try:
        # --allowedTools "Edit(CLAUDE.md)" scopes write access to just this
        # file, so claude -p can actually create it instead of stopping to
        # ask for permission it can't get non-interactively.
        result = subprocess.run(
            ["claude", "-p", prompt_text, "--allowedTools", "Edit(CLAUDE.md)"],
            capture_output=True,
            text=True,
            timeout=600,
            shell=(sys.platform == "win32"),
        )
        log = (result.stdout or "") + (result.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        log = str(exc)

    if CLAUDE_MD.exists():
        ui.ok("CLAUDE.md generated - review it")
    else:
        ui.warn("claude -p didn't create CLAUDE.md - see below, or use the prompt instead")
        ui.console.print(escape(log))
        _show_prompt(COPY_LEAD)
