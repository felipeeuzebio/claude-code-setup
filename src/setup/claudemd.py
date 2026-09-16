"""CLAUDE.md steps: generating this repo's own CLAUDE.md from
CLAUDE_TEMPLATE.md, and maintaining the web/search/browser tool-routing
block in the user's global ~/.claude/CLAUDE.md.

Internal-only, called from setup's own CLAUDE.md steps.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from rich.markup import escape

from setup import ui
from setup.mcpservers import REPO_ROOT

PROMPT_FILE = REPO_ROOT / "CLAUDE_TEMPLATE.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
COPY_LEAD = (
    "Copy this into any Claude Code session (here or another project) "
    "whenever you want to generate a CLAUDE.md:"
)
# The template tells Claude to summarize and wait for confirmation when a
# CLAUDE.md exists; `claude -p` can't ask, so the y/n happens in the terminal
# first and this line hands the answer over.
REFRESH_LEAD = (
    "\n\nCLAUDE.md already exists and the user has confirmed the refresh: "
    "update it in place, keep every hand-written line that still matches the "
    "repo, change only what no longer does, and don't stop to ask again."
)

# Same shape as codegraph's own installer block in ~/.claude/CLAUDE.md:
# marker-delimited so re-running setup rewrites just this block and leaves
# hand-written content around it alone.
WEB_TOOLS_START = "<!-- WEB_TOOLS_START -->"
WEB_TOOLS_END = "<!-- WEB_TOOLS_END -->"

WEB_TOOLS_HEADING = "## Web Fetching, Search & Browser Tools"
# Ordering is measured, not assumed: bench/web_tools showed built-in WebFetch
# is correct and 5-40x cheaper than a browser tool on a static page, and
# WebSearch matches Firecrawl search - but WebFetch can't run JavaScript and
# returns a summary, not the page. bench/docs_retrieval showed Context7 beats
# both a live scrape and a local mirror on library docs. See AGENTS.md.
WEB_TOOLS_INTRO = (
    "Default to WebSearch/WebFetch - cheapest and fastest for a search or a "
    "single page. WebFetch summarizes rather than returning the page "
    "verbatim, and can't run JavaScript, so client-rendered pages come back "
    "empty. Escalate to a registered MCP server only then - each ships its "
    "own tool instructions:"
)
WEB_TOOLS_FALLBACK = (
    "Don't reach for a browser tool on a plain fetch or search - same "
    "answer, more tokens and time."
)

# Keys match mcp-servers.json / build_plan() names; order here is the order
# the bullets are written in.
WEB_TOOL_BULLETS: dict[str, str] = {
    "context7": (
        "- **Context7** (`resolve-library-id` -> `query-docs`): library/"
        "framework/SDK docs, before any web tool - relevant passages, not "
        "whole pages."
    ),
    "lightpanda": (
        "- **Lightpanda** (`mcp__lightpanda__*`): first escalation for a "
        "page - JS-rendered, verbatim markdown, or scripted navigate/click/"
        "extract. Single binary, cheap to run."
    ),
    "browser-use": (
        "- **browser-use** (`browser_exec`/`browser_screenshot`): real "
        "interaction only - clicking, typing, a logged-in session, or "
        "open-ended scraping."
    ),
}


def _show_prompt(lead: str) -> None:
    ui.console.print(f"  {lead}")
    # Restores gum format's Markdown rendering, dropped nowhere else in
    # this rewrite - `rich` covers it directly.
    ui.render_markdown(PROMPT_FILE.read_text(encoding="utf-8"))


def _run_claude_p(prompt_text: str) -> str:
    """Runs claude -p with write access scoped to CLAUDE.md; returns its log.
    No --model: the CLAUDE.md is meant to come from the user's default model."""
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
        return (result.stdout or "") + (result.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)


def ensure_claude_md() -> None:
    exists = CLAUDE_MD.exists()

    if not sys.stdin.isatty():
        if exists:
            ui.skip("CLAUDE.md already exists - not touching it outside a terminal")
        else:
            _show_prompt(
                "Not an interactive terminal - here's the prompt, paste it into "
                "any Claude Code session when you're ready:"
            )
        return

    question = (
        "CLAUDE.md already exists - refresh it with Claude Code? "
        "(only lines that no longer match the repo change)"
        if exists
        else "Initialize CLAUDE.md for this repo now with Claude Code?"
    )
    if not ui.confirm(question):
        if exists:
            ui.skip("CLAUDE.md left as is")
        else:
            _show_prompt(COPY_LEAD)
        return

    if not shutil.which("claude"):
        ui.warn("claude CLI not found on PATH - here's the prompt instead")
        _show_prompt(COPY_LEAD)
        return

    prompt_text = PROMPT_FILE.read_text(encoding="utf-8")
    before = CLAUDE_MD.read_text(encoding="utf-8") if exists else None
    log = _run_claude_p(prompt_text + REFRESH_LEAD if exists else prompt_text)
    after = CLAUDE_MD.read_text(encoding="utf-8") if CLAUDE_MD.exists() else None

    if after is None:
        ui.warn("claude -p didn't create CLAUDE.md - see below, or use the prompt instead")
        ui.console.print(escape(log))
        _show_prompt(COPY_LEAD)
    elif before is None:
        ui.ok("CLAUDE.md generated - review it")
    elif after == before:
        ui.skip("claude -p left CLAUDE.md unchanged - it already matched the repo")
    else:
        ui.ok("CLAUDE.md refreshed - review the diff (git diff CLAUDE.md)")


def _global_claude_md(env: dict[str, str]) -> Path:
    # CLAUDE_HOME is a testability seam only - same one mcpconfig uses.
    home = env.get("CLAUDE_HOME")
    base = Path(home) if home else Path.home()
    return base / ".claude" / "CLAUDE.md"


def _render_block(names: list[str]) -> str:
    bullets = "\n".join(WEB_TOOL_BULLETS[name] for name in names)
    return "\n".join(
        [
            WEB_TOOLS_START,
            WEB_TOOLS_HEADING,
            "",
            WEB_TOOLS_INTRO,
            "",
            bullets,
            "",
            WEB_TOOLS_FALLBACK,
            WEB_TOOLS_END,
        ]
    )


def _replace_block(existing: str, block: str, start_marker: str, end_marker: str) -> str:
    """Swaps the marked block in `existing` for `block`, appending it as a new
    section when no markers are there yet. An empty `block` removes it."""
    start = existing.find(start_marker)
    end = existing.find(end_marker)

    if start != -1 and end > start:
        before = existing[:start].rstrip("\n")
        after = existing[end + len(end_marker) :].lstrip("\n")
        parts = [part for part in (before, block, after) if part]
        return "\n\n".join(parts) + "\n"

    if not block:
        return existing
    head = existing.rstrip("\n")
    return f"{head}\n\n{block}\n" if head else f"{block}\n"


def ensure_web_tools_guidance(registered: list[str], env: dict[str, str] | None = None, ask: bool = False) -> None:
    """Writes the web/search/browser tool-routing block into the global
    ~/.claude/CLAUDE.md, listing only servers that actually got registered.

    When ask=True and in an interactive terminal, prompts the user first.

    Nothing outside the markers is touched, and a run that registers none of
    them drops the block rather than leaving advice pointing at absent tools -
    the same reasoning that keeps unready servers out of ~/.claude.json.
    """
    if env is None:
        env = dict(os.environ)

    names = [name for name in WEB_TOOL_BULLETS if name in registered]
    path = _global_claude_md(env)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""

    # Prompt if requested and in an interactive terminal
    if ask and sys.stdin.isatty():
        if names:
            question = f"Write web/browser tool guidance to {path}? ({', '.join(names)})"
        else:
            ui.skip("No web/browser servers registered - skipping")
            return
        if not ui.confirm(question):
            ui.skip("Skipped")
            return

    block = _render_block(names) if names else ""
    updated = _replace_block(existing, block, WEB_TOOLS_START, WEB_TOOLS_END)

    if updated == existing:
        ui.skip(f"{path} already current")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")

    if names:
        ui.ok(f"Web/browser tool guidance written to {path} ({', '.join(names)})")
    else:
        ui.skip(f"No web/browser servers registered - guidance block removed from {path}")

