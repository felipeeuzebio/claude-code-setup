"""Unit tests for ui.choose, the arrow-key menu."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from prompt_toolkit.input import PipeInput, create_pipe_input
from prompt_toolkit.output import DummyOutput

from claude_code_setup.core import ui

DOWN = "\x1b[B"
UP = "\x1b[A"
ENTER = "\r"


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[PipeInput]:
    """A terminal session whose keypresses the test types in advance."""
    monkeypatch.setattr(ui.console, "_force_terminal", True)
    with create_pipe_input() as pipe:
        yield pipe


def _choose(keys: PipeInput, typed: str, default: int = 0) -> int:
    keys.send_text(typed)
    return ui.choose("Pick one", ["first", "second", "third"], default, input=keys, output=DummyOutput())


def test_enter_picks_the_default(keys: PipeInput) -> None:
    assert _choose(keys, ENTER) == 0


def test_enter_picks_a_non_zero_default(keys: PipeInput) -> None:
    assert _choose(keys, ENTER, default=2) == 2


def test_arrow_keys_move_the_selection(keys: PipeInput) -> None:
    assert _choose(keys, DOWN + DOWN + UP + ENTER) == 1


def test_non_terminal_returns_the_default_without_prompting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui.console, "_force_terminal", False)
    monkeypatch.setattr(ui.questionary, "select", lambda *_a, **_k: pytest.fail("prompted anyway"))

    assert ui.choose("Pick one", ["first", "second"], default=1) == 1


def test_menu_shows_the_key_legend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui.console, "_force_terminal", True)
    seen: dict = {}

    class _Answered:
        def unsafe_ask(self) -> int:
            return 0

    def fake_select(*_a: object, **kwargs: object) -> _Answered:
        seen.update(kwargs)
        return _Answered()

    monkeypatch.setattr(ui.questionary, "select", fake_select)
    ui.choose("Pick one", ["first", "second"])

    assert seen["instruction"] == "↑↓ Move with arrow keys ENTER Select Ctrl+C Quit"
