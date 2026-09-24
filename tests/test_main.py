"""Unit tests for main()'s mode choice and project-dir resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_code_setup import main as setup_main


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
