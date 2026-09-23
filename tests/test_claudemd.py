"""Unit tests for the global ~/.claude/CLAUDE.md web-tools guidance block."""

from __future__ import annotations

from pathlib import Path

import sys

import pytest

from claude_code_setup import claudemd
from claude_code_setup.claudemd import (
    REFRESH_LEAD,
    WEB_TOOLS_END,
    WEB_TOOLS_START,
    ensure_claude_md,
    ensure_web_tools_guidance,
)

ALL_THREE = ["context7", "lightpanda", "browser-use"]
CODEGRAPH_BLOCK = (
    "<!-- CODEGRAPH_START -->\n## CodeGraph\n\nHand-written.\n<!-- CODEGRAPH_END -->\n"
)


def _target(tmp_path: Path) -> Path:
    return tmp_path / ".claude" / "CLAUDE.md"


def _run(tmp_path: Path, registered: list[str]) -> str:
    ensure_web_tools_guidance(registered, env={"CLAUDE_HOME": str(tmp_path)})
    target = _target(tmp_path)
    return target.read_text(encoding="utf-8") if target.exists() else ""


def test_creates_file_with_only_registered_servers(tmp_path: Path) -> None:
    content = _run(tmp_path, ["lightpanda", "github"])

    assert WEB_TOOLS_START in content and WEB_TOOLS_END in content
    assert "Lightpanda" in content
    assert "Context7" not in content
    assert "browser_exec" not in content


def test_block_puts_built_ins_before_any_server(tmp_path: Path) -> None:
    # The routing order is the point of the block (see bench/web_tools):
    # built-in WebSearch/WebFetch first, servers only as escalation.
    content = _run(tmp_path, ALL_THREE)

    assert content.index("Default to WebSearch/WebFetch") < content.index("- **Context7**")
    assert "can't run JavaScript" in content
    assert "Firecrawl" not in content


def test_appends_below_existing_content_without_touching_it(tmp_path: Path) -> None:
    target = _target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_text(CODEGRAPH_BLOCK, encoding="utf-8")

    content = _run(tmp_path, ALL_THREE)

    assert content.startswith(CODEGRAPH_BLOCK.rstrip("\n"))
    assert content.index("## CodeGraph") < content.index(WEB_TOOLS_START)


def test_rerun_replaces_block_in_place_rather_than_duplicating(tmp_path: Path) -> None:
    _run(tmp_path, ALL_THREE)
    content = _run(tmp_path, ["browser-use"])

    assert content.count(WEB_TOOLS_START) == 1
    assert "Lightpanda" not in content


def test_block_is_removed_when_no_web_server_is_registered(tmp_path: Path) -> None:
    target = _target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_text(CODEGRAPH_BLOCK, encoding="utf-8")
    _run(tmp_path, ALL_THREE)

    content = _run(tmp_path, ["github"])

    assert WEB_TOOLS_START not in content
    assert "## CodeGraph" in content


def test_no_file_is_created_when_nothing_to_write(tmp_path: Path) -> None:
    _run(tmp_path, [])

    assert not _target(tmp_path).exists()


def test_rerun_with_same_servers_leaves_file_byte_identical(tmp_path: Path) -> None:
    first = _run(tmp_path, ALL_THREE)
    second = _run(tmp_path, ALL_THREE)

    assert first == second


# --- ensure_claude_md: the repo-level file ---------------------------------


@pytest.fixture
def claude_p(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stands in for an interactive run with `claude` on PATH; records the
    prompt `claude -p` would have received instead of spawning it."""
    seen: dict = {"prompts": [], "confirm": True}
    monkeypatch.setattr(claudemd, "CLAUDE_MD", tmp_path / "CLAUDE.md")
    monkeypatch.setattr(claudemd, "PROMPT_FILE", tmp_path / "CLAUDE_TEMPLATE.md")
    claudemd.PROMPT_FILE.write_text("TEMPLATE\n", encoding="utf-8")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(claudemd.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claudemd.ui, "confirm", lambda *_a, **_k: seen["confirm"])

    def fake_run(prompt: str) -> str:
        seen["prompts"].append(prompt)
        claudemd.CLAUDE_MD.write_text("# generated\n", encoding="utf-8")
        return ""

    monkeypatch.setattr(claudemd, "_run_claude_p", fake_run)
    return seen


def test_existing_claude_md_is_refreshed_with_confirmation_handed_over(claude_p: dict) -> None:
    claudemd.CLAUDE_MD.write_text("# old\n", encoding="utf-8")

    ensure_claude_md()

    assert claude_p["prompts"] == ["TEMPLATE\n" + REFRESH_LEAD]
    assert claudemd.CLAUDE_MD.read_text(encoding="utf-8") == "# generated\n"


def test_fresh_claude_md_gets_the_plain_template(claude_p: dict) -> None:
    ensure_claude_md()

    assert claude_p["prompts"] == ["TEMPLATE\n"]


def test_declined_refresh_never_runs_claude(claude_p: dict) -> None:
    claudemd.CLAUDE_MD.write_text("# old\n", encoding="utf-8")
    claude_p["confirm"] = False

    ensure_claude_md()

    assert claude_p["prompts"] == []
    assert claudemd.CLAUDE_MD.read_text(encoding="utf-8") == "# old\n"
