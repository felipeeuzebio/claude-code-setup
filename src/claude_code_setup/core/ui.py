"""Styled terminal output - replaces gum entirely.

Every current gum use (colored ok/skip/warn/step lines, a spinner, a y/n
confirm, Markdown rendering) is a strict match here via `rich`, with no
external binary/download/temp-dir lifecycle to manage. `Console` already
auto-detects TTY and honors NO_COLOR itself, so there's a single
library-owned color-gating rule instead of three slightly different
hand-rolled ones (bash/Python/PowerShell today).

The one thing rich can't do is an arrow-key menu, so `choose` is a small
prompt_toolkit Application (which handles the Windows console too). Not
questionary: it can't put a legend below the options, and it paints the
default choice with prompt_toolkit's reverse-video "selected" class.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.prompt import Confirm

console = Console()
_err_console = Console(stderr=True)

T = TypeVar("T")

# ANSI color names, not hex, so the menu follows the terminal's own palette
# like rich's output does. The legend's arrows are the one exception to the
# ASCII-only rule below: prompt_toolkit writes through WriteConsoleW on
# legacy Windows consoles and encodes with errors="replace" elsewhere, so an
# unrenderable glyph degrades to "?" instead of raising.
# (key, what it does) pairs, rendered as "↑↓ Move with arrow keys ENTER ...".
MENU_LEGEND = (("↑↓", "Move with arrow keys"), ("ENTER", "Select"), ("Ctrl+C", "Quit"))
_MENU_STYLE = Style(
    [
        ("qmark", "fg:ansimagenta bold"),
        ("question", "bold"),
        ("pointer", "fg:ansigreen bold"),
        ("highlighted", "fg:ansigreen bold"),
        ("legend.key", "bold"),
        ("legend", "fg:ansibrightblack"),
    ]
)


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


def _menu_tokens(prompt: str, options: list[str], at: int) -> list[tuple[str, str]]:
    """The whole menu as styled text: question, options with a ">" on the
    pointed one, and the key legend as the last line."""
    tokens: list[tuple[str, str]] = [("class:qmark", "  ? "), ("class:question", prompt), ("", "\n")]
    for index, option in enumerate(options):
        if index == at:
            tokens += [("class:pointer", "  > "), ("class:highlighted", option)]
        else:
            tokens += [("", "    "), ("", option)]
        tokens.append(("", "\n"))
    tokens.append(("", "  "))
    for position, (key, action) in enumerate(MENU_LEGEND):
        separator = " " if position else ""
        tokens += [("class:legend", separator), ("class:legend.key", key), ("class:legend", f" {action}")]
    return tokens


def _run_menu(prompt: str, options: list[str], default: int, **session: Any) -> int:
    at = default
    bindings = KeyBindings()

    @bindings.add("up")
    @bindings.add("k")
    def _up(_event: KeyPressEvent) -> None:
        nonlocal at
        at = (at - 1) % len(options)

    @bindings.add("down")
    @bindings.add("j")
    def _down(_event: KeyPressEvent) -> None:
        nonlocal at
        at = (at + 1) % len(options)

    @bindings.add("enter")
    def _pick(event: KeyPressEvent) -> None:
        event.app.exit(result=at)

    @bindings.add("c-c")
    def _quit(event: KeyPressEvent) -> None:
        event.app.exit(exception=KeyboardInterrupt())

    control = FormattedTextControl(lambda: _menu_tokens(prompt, options, at), show_cursor=False)
    app: Application[int] = Application(
        layout=Layout(Window(control)),
        key_bindings=bindings,
        style=_MENU_STYLE,
        erase_when_done=True,
        **session,
    )
    return app.run()


def choose(prompt: str, options: list[str], default: int = 0, **session: Any) -> int:
    """Arrow-key menu: up/down (or j/k) to move, Enter to pick, legend at the
    bottom. Returns the picked option's index, or `default` if stdin isn't
    interactive. Ctrl-C aborts setup, same as at any other prompt.

    `session` goes to prompt_toolkit's Application (input=/output=) - a test
    seam only."""
    if not console.is_terminal:
        return default
    try:
        picked = _run_menu(prompt, options, default, **session)
    except EOFError:
        return default
    # The menu erases itself; leave a one-line record of the answer instead.
    console.print(f"  [bold magenta]?[/bold magenta] [bold]{escape(prompt)}[/bold] [green]{escape(options[picked])}[/green]")
    return picked


def spin(title: str, fn: Callable[[], T]) -> T:
    """Runs fn() with a spinner; falls back to a plain line when not a TTY."""
    if not console.is_terminal:
        console.print(f"  ... {escape(title)}")
        return fn()
    with console.status(f"  {escape(title)}", spinner="line"):
        return fn()


def render_markdown(text: str) -> None:
    console.print(Markdown(text))
