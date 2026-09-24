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


def test_j_and_k_move_like_the_arrows(keys: PipeInput) -> None:
    assert _choose(keys, "jjk" + ENTER) == 1


def test_ctrl_c_quits(keys: PipeInput) -> None:
    with pytest.raises(KeyboardInterrupt):
        _choose(keys, "\x03")


def test_non_terminal_returns_the_default_without_prompting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui.console, "_force_terminal", False)
    monkeypatch.setattr(ui, "_run_menu", lambda *_a, **_k: pytest.fail("prompted anyway"))

    assert ui.choose("Pick one", ["first", "second"], default=1) == 1


def _text(tokens: list[tuple[str, str]]) -> str:
    return "".join(text for _style, text in tokens)


def test_legend_is_the_last_line_below_the_options() -> None:
    lines = _text(ui._menu_tokens("Pick one", ["first", "second"], 0)).splitlines()

    assert lines[-1].strip() == "↑↓ Move with arrow keys ENTER Select Ctrl+C Quit"
    assert "Pick one" in lines[0]
    assert [line.strip(" >") for line in lines[1:3]] == ["first", "second"]


def test_only_the_pointed_option_is_marked() -> None:
    lines = _text(ui._menu_tokens("Pick one", ["first", "second"], 1)).splitlines()

    assert lines[1].startswith("    first")
    assert lines[2].startswith("  > second")


def test_no_option_uses_the_reverse_video_selected_class() -> None:
    # prompt_toolkit's own "selected" class renders as a white reverse-video bar.
    tokens = ui._menu_tokens("Pick one", ["first", "second"], 0)
    assert all("selected" not in style for style, _text in tokens)
