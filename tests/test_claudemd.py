"""Unit tests for the global ~/.claude/CLAUDE.md web-tools guidance block."""

from __future__ import annotations

from pathlib import Path

import sys

import pytest

from claude_code_setup import claudemd
from claude_code_setup.claudemd import (
    CLAUDE_MD_END,
    CLAUDE_MD_START,
    OUTPUT_LEAD,
    REFRESH_LEAD,
    WEB_TOOLS_END,
    WEB_TOOLS_START,
    _extract_claude_md,
    claude_md_target,
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


# --- ensure_claude_md: the project's own file -----------------------------


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch project dir, as if setup was run from inside it."""
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setattr(claudemd, "PROMPT_FILE", tmp_path / "CLAUDE_TEMPLATE.md")
    claudemd.PROMPT_FILE.write_text("TEMPLATE\n", encoding="utf-8")
    return proj


def _reply(content: str) -> str:
    """What claude -p prints: some chatter, then the file between markers."""
    return f"Here it is.\n{CLAUDE_MD_START}\n{content}{CLAUDE_MD_END}\nDone.\n"


@pytest.fixture
def claude_p(project: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stands in for an interactive run with `claude` on PATH; records what
    `claude -p` would have received instead of spawning it."""
    seen: dict = {"calls": [], "confirm": True, "reply": _reply("# generated\n")}
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(claudemd.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claudemd.ui, "confirm", lambda *_a, **_k: seen["confirm"])

    def fake_run(prompt: str, cwd: Path) -> str:
        seen["calls"].append((prompt, cwd))
        return seen["reply"]

    monkeypatch.setattr(claudemd, "_run_claude_p", fake_run)
    return seen


def test_target_is_dot_claude_when_there_is_no_claude_md(project: Path) -> None:
    assert claude_md_target(project) == project / ".claude" / "CLAUDE.md"


def test_target_is_root_when_root_claude_md_exists(project: Path) -> None:
    (project / "CLAUDE.md").write_text("# root\n", encoding="utf-8")
    (project / ".claude").mkdir()
    (project / ".claude" / "CLAUDE.md").write_text("# nested\n", encoding="utf-8")

    assert claude_md_target(project) == project / "CLAUDE.md"


def test_fresh_project_gets_dot_claude_claude_md(project: Path, claude_p: dict) -> None:
    ensure_claude_md(project)

    [(prompt, cwd)] = claude_p["calls"]
    assert cwd == project
    assert prompt == "TEMPLATE\n" + OUTPUT_LEAD.format(target=".claude/CLAUDE.md")
    assert (project / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "# generated\n"
    assert not (project / "CLAUDE.md").exists()


def test_existing_root_claude_md_is_refreshed_in_place(project: Path, claude_p: dict) -> None:
    (project / "CLAUDE.md").write_text("# old\n", encoding="utf-8")

    ensure_claude_md(project)

    [(prompt, _cwd)] = claude_p["calls"]
    assert prompt == "TEMPLATE\n" + OUTPUT_LEAD.format(target="CLAUDE.md") + REFRESH_LEAD
    assert (project / "CLAUDE.md").read_text(encoding="utf-8") == "# generated\n"
    assert not (project / ".claude").exists()


def test_existing_dot_claude_claude_md_is_refreshed(project: Path, claude_p: dict) -> None:
    (project / ".claude").mkdir()
    (project / ".claude" / "CLAUDE.md").write_text("# old\n", encoding="utf-8")

    ensure_claude_md(project)

    [(prompt, _cwd)] = claude_p["calls"]
    assert ".claude/CLAUDE.md" in prompt
    assert prompt.endswith(REFRESH_LEAD)
    assert (project / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "# generated\n"


def test_declined_refresh_never_runs_claude(project: Path, claude_p: dict) -> None:
    (project / "CLAUDE.md").write_text("# old\n", encoding="utf-8")
    claude_p["confirm"] = False

    ensure_claude_md(project)

    assert claude_p["calls"] == []
    assert (project / "CLAUDE.md").read_text(encoding="utf-8") == "# old\n"


def test_reply_without_markers_leaves_the_file_alone(project: Path, claude_p: dict) -> None:
    (project / "CLAUDE.md").write_text("# old\n", encoding="utf-8")
    claude_p["reply"] = "I couldn't do it.\n"

    ensure_claude_md(project)

    assert (project / "CLAUDE.md").read_text(encoding="utf-8") == "# old\n"


def test_extract_takes_the_last_marked_block_and_drops_a_code_fence() -> None:
    reply = (
        f"I'll wrap it in {CLAUDE_MD_START} ... {CLAUDE_MD_END} as asked.\n"
        f"{CLAUDE_MD_START}\n```markdown\n# Title\n\nBody\n```\n{CLAUDE_MD_END}\n"
    )
    assert _extract_claude_md(reply) == "# Title\n\nBody\n"


def test_extract_returns_none_for_an_empty_or_missing_block() -> None:
    assert _extract_claude_md("no markers here") is None
    assert _extract_claude_md(f"{CLAUDE_MD_START}\n\n{CLAUDE_MD_END}") is None
