"""Unit tests for starting the Bifrost gateway in the background."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_code_setup import bifrost


def test_bifrost_does_not_run_inside_the_temporary_install_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # It outlives setup, and the installer deletes its download on exit -
    # node errors out once its cwd is gone.
    seen: dict = {}
    monkeypatch.setattr(bifrost.subprocess, "Popen", lambda cmd, **kwargs: seen.update(kwargs))

    bifrost.start_background(tmp_path / "bifrost.log")

    assert seen["cwd"] == Path.home()
