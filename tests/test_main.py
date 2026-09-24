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


# --- optional pieces are asked about, not configured ------------------------


@pytest.fixture
def linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_main.sys, "platform", "linux")


def test_declined_lightpanda_is_never_installed(linux: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_main.shutil, "which", lambda _: None)
    monkeypatch.setattr(setup_main.ui, "confirm", lambda *_a, **_k: False)
    monkeypatch.setattr(setup_main, "_install_tool", lambda *_a: pytest.fail("installed anyway"))

    assert setup_main._lightpanda_step() is False


def test_installed_lightpanda_is_used_without_asking(linux: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_main.shutil, "which", lambda _: "/usr/bin/lightpanda")
    monkeypatch.setattr(setup_main.ui, "confirm", lambda *_a, **_k: pytest.fail("asked anyway"))

    assert setup_main._lightpanda_step() is True


def test_accepted_lightpanda_is_installed(linux: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_main.shutil, "which", lambda _: None)
    monkeypatch.setattr(setup_main.ui, "confirm", lambda *_a, **_k: True)
    monkeypatch.setattr(setup_main, "_install_tool", lambda *_a: True)

    assert setup_main._lightpanda_step() is True


def test_declined_bifrost_is_never_started(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_main.bifrost, "is_running", lambda: False)
    monkeypatch.setattr(setup_main.ui, "confirm", lambda *_a, **_k: False)
    monkeypatch.setattr(setup_main.bifrost, "start_background", lambda _p: pytest.fail("started anyway"))

    assert setup_main._bifrost_step() is False


def test_running_bifrost_is_kept_without_asking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_main.bifrost, "is_running", lambda: True)
    monkeypatch.setattr(setup_main.ui, "confirm", lambda *_a, **_k: pytest.fail("asked anyway"))

    assert setup_main._bifrost_step() is True


# --- Ctrl+C -----------------------------------------------------------------


def test_ctrl_c_exits_130_without_a_traceback(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def interrupted() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(setup_main, "_run", interrupted)

    with pytest.raises(SystemExit) as exit_info:
        setup_main.main()

    assert exit_info.value.code == 130
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out + captured.err
    assert "Setup cancelled" in captured.out
