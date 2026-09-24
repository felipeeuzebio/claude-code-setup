"""Unit tests for main()'s mode choice and project-dir resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_code_setup import main as setup_main


def test_flag_picks_claude_md_only_without_asking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_main.ui, "choose", lambda *_a, **_k: pytest.fail("asked anyway"))
    assert setup_main._choose_mode(claude_md_only=True) == "claude-md"


def test_non_interactive_run_defaults_to_full(monkeypatch: pytest.MonkeyPatch) -> None:
    # ui.choose returns its default when there's no terminal to ask on.
    monkeypatch.setattr(setup_main.ui, "choose", lambda _p, _o, default=0: default)
    assert setup_main._choose_mode(claude_md_only=False) == "full"


@pytest.mark.parametrize(("picked", "mode"), [(0, "full"), (1, "claude-md")])
def test_interactive_choice_maps_to_mode(monkeypatch: pytest.MonkeyPatch, picked: int, mode: str) -> None:
    monkeypatch.setattr(setup_main.ui, "choose", lambda *_a, **_k: picked)
    assert setup_main._choose_mode(claude_md_only=False) == mode


def test_project_dir_comes_from_the_wrapper_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SETUP_PROJECT_DIR", str(tmp_path))
    assert setup_main._project_dir() == tmp_path.resolve()


def test_project_dir_falls_back_to_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_SETUP_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert setup_main._project_dir() == tmp_path.resolve()


def test_home_dir_is_never_treated_as_a_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_main.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("CLAUDE_CODE_SETUP_PROJECT_DIR", str(tmp_path))
    assert setup_main._project_dir() is None
