"""Styled terminal output - replaces gum entirely.

Every current gum use (colored ok/skip/warn/step lines, a spinner, a y/n
confirm, Markdown rendering) is a strict match here via `rich`, with no
external binary/download/temp-dir lifecycle to manage. `Console` already
auto-detects TTY and honors NO_COLOR itself, so there's a single
library-owned color-gating rule instead of three slightly different
hand-rolled ones (bash/Python/PowerShell today).
"""

from __future__ import annotations

from typing import Callable, TypeVar

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.prompt import Confirm

console = Console()
_err_console = Console(stderr=True)

T = TypeVar("T")


# Plain ASCII glyphs throughout (+/-/!, "line" spinner frames), never
# Unicode symbols: Windows' legacy console encoding (cp1252) can't render
# things like a Unicode checkmark and raises UnicodeEncodeError outright -
# setup.ps1's own gum-styled path already avoided this same trap.
#
# Every dynamic string passed in here is escaped before being embedded in
# markup: Console.print() treats "[...]" as a style tag by default, so an
# unescaped message like "browser-use[cli]" silently loses the "[cli]"
# (parsed as an unknown, dropped tag) instead of printing it literally.


def ok(msg: str) -> None:
    console.print(f"  [green]+[/green] {escape(msg)}")


def skip(msg: str) -> None:
    console.print(f"  [dim]-  {escape(msg)}[/dim]")


def warn(msg: str) -> None:
    _err_console.print(f"  [yellow]![/yellow] {escape(msg)}")


def step(msg: str) -> None:
    console.print()
    console.print(f"[bold magenta]==> {escape(msg)}[/bold magenta]")


def ok_ver(name: str, version: str) -> None:
    console.print(f"  [green]+[/green] {escape(name)} [dim]{escape(version)}[/dim]")


def confirm(prompt: str, default: bool = False) -> bool:
    """Asks a y/n question; returns `default` if stdin isn't interactive."""
    if not console.is_terminal:
        return default
    try:
        return Confirm.ask(f"  {escape(prompt)}", default=default, console=console)
    except EOFError:
        return default


def spin(title: str, fn: Callable[[], T]) -> T:
    """Runs fn() with a spinner; falls back to a plain line when not a TTY."""
    if not console.is_terminal:
        console.print(f"  ... {escape(title)}")
        return fn()
    with console.status(f"  {escape(title)}", spinner="line"):
        return fn()


def render_markdown(text: str) -> None:
    console.print(Markdown(text))
