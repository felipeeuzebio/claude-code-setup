"""One-shot setup for this Claude Code environment - Linux/WSL2/macOS/native
Windows alike. Installs what it can, registers what it can into
~/.claude.json, and prints exactly what's left to do by hand.

This is the single orchestration spine that used to be duplicated between
setup.sh and setup.ps1: one codebase, branching on `sys.platform` only
where behavior genuinely differs (Lightpanda: Linux/Darwin only; the
codegraph installer one-liner: curl|bash vs irm|iex).

Asks up front whether to run the full setup or just generate/refresh the
CLAUDE.md of the project it was launched from (`--claude-md-only` skips the
question).

Optional config via env vars or a repo-root .env file (see .env.example):
  GITHUB_TOKEN,
  SKIP_BIFROST=1, SKIP_LIGHTPANDA=1
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.markup import escape

from claude_code_setup import bifrost, claudemd
from claude_code_setup.core import sysinfo, ui
from claude_code_setup.core.envfile import apply_env, load_env
from claude_code_setup.mcp import config as mcp_config
from claude_code_setup.mcp.servers import REPO_ROOT

_SHELL = sys.platform == "win32"

MODE_FULL = "full"
MODE_CLAUDE_MD = "claude-md"
_MODE_OPTIONS = [
    (MODE_FULL, "Full setup (tools, MCP servers, Bifrost, CLAUDE.md)"),
    (MODE_CLAUDE_MD, "Just generate/refresh this project's CLAUDE.md"),
]


def _project_dir() -> Path | None:
    """The directory setup was launched from. setup.sh/setup.ps1 cd into the
    repo before `uv run`, so they pass the caller's dir along in
    CLAUDE_CODE_SETUP_PROJECT_DIR. None for the home dir - that's where a
    bare `curl | bash` usually runs, and it's no project."""
    raw = os.environ.get("CLAUDE_CODE_SETUP_PROJECT_DIR")
    project = (Path(raw) if raw else Path.cwd()).resolve()
    return None if project == Path.home().resolve() else project


def _choose_mode(claude_md_only: bool) -> str:
    """Flag first, then ask; a non-interactive run gets the full setup."""
    if claude_md_only:
        return MODE_CLAUDE_MD
    picked = ui.choose("What should setup do?", [label for _, label in _MODE_OPTIONS])
    return _MODE_OPTIONS[picked][0]


def _claude_md_step(project: Path | None) -> None:
    if project is None:
        ui.step("CLAUDE.md")
        ui.skip("Launched from your home dir - re-run from inside a project to generate its CLAUDE.md")
        return
    ui.step(f"CLAUDE.md for {project}")
    claudemd.ensure_claude_md(project)


def _install_tool(cmd: str, unix_url: str, windows_url: str) -> bool:
    """Installs `cmd` from a curl|bash (unix) or irm|iex (Windows)
    one-liner unless it's already on PATH. Prints an ok line either way and
    returns whether it's available afterward."""
    if shutil.which(cmd):
        ui.ok(f"{cmd} already installed")
        return True
    if sys.platform == "win32":
        script = f"irm {windows_url} | iex"
        ui.spin(
            f"Installing {cmd}...",
            lambda: subprocess.run(["powershell", "-NoProfile", "-Command", script]),
        )
    else:
        script = f"curl -fsSL '{unix_url}' | bash"
        ui.spin(f"Installing {cmd}...", lambda: subprocess.run(["bash", "-c", script]))
    found = shutil.which(cmd) is not None
    if found:
        ui.ok(f"{cmd} installed")
    return found


def _git_hook_step() -> None:
    ui.step("Git commit-msg hook")
    if not shutil.which("git"):
        ui.skip("git not available")
        return
    inside_work_tree = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
    )
    if inside_work_tree.returncode == 0:
        subprocess.run(["git", "-C", str(REPO_ROOT), "config", "core.hooksPath", "githooks"])
        ui.ok("commit-msg now enforces Conventional Commits (see githooks/commit-msg)")
    else:
        ui.skip("Not a git checkout")


def _required_tools_step() -> bool:
    """Exits on a missing hard requirement; returns whether uvx is available."""
    ui.step("Checking required tools")

    found, version = sysinfo.check_tool("node")
    if not found:
        ui.warn("node is required - install it first (https://nodejs.org)")
        sys.exit(1)
    ui.ok_ver("node", version)

    found, version = sysinfo.check_tool("npx")
    if not found:
        ui.warn("npx is required - it ships with node >=8.2")
        sys.exit(1)
    ui.ok_ver("npx", version)

    has_uvx, uvx_version = sysinfo.check_tool("uvx")
    if has_uvx:
        ui.ok_ver("uvx", uvx_version)
    else:
        ui.warn(
            "uvx not available - browser-use (self-hosted) will be skipped "
            "(install: https://docs.astral.sh/uv/)"
        )

    return has_uvx


def _codegraph_step(project: Path | None) -> None:
    ui.step("Codegraph")
    unix_url = "https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh"
    windows_url = "https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.ps1"

    if not _install_tool("codegraph", unix_url, windows_url):
        ui.warn("codegraph install failed - skipping registration")
        return

    # codegraph's own installer prints a multi-line status box (its own
    # terminal UI, not ours) - the spinner hides it and only surfaces it on failure.
    ui.spin(
        "Registering codegraph in Claude Code...",
        lambda: subprocess.run(
            ["codegraph", "install", "--target", "claude", "--location", "global", "-y"],
            capture_output=True,
            shell=_SHELL,
        ),
    )
    ui.ok("codegraph registered in Claude Code")

    if project is None:
        ui.console.print("  Run 'codegraph init' in any project whenever you want to index it.")
        return
    # init builds an index from scratch, sync refreshes the existing one.
    cg_action = "sync" if (project / ".codegraph").is_dir() else "init"
    if not sys.stdin.isatty():
        ui.console.print(
            escape(
                f"  Run 'codegraph {cg_action}' in {project} (or any project) "
                "whenever you want to build/refresh its index."
            )
        )
    elif ui.confirm(f"Run 'codegraph {cg_action}' for {project} now?"):
        ui.spin(
            f"Running codegraph {cg_action}...",
            lambda: subprocess.run(["codegraph", cg_action], cwd=project, shell=_SHELL),
        )
        ui.ok(f"codegraph {cg_action} complete")
    else:
        ui.skip(f"Skipped - run 'codegraph {cg_action}' in {project} anytime")


def _browser_use_step(has_uvx: bool) -> bool:
    ui.step("browser-use (self-hosted, Claude-driven browser control)")
    bu_install = ["uvx", "--python", "3.12", "browser-use[cli]", "install"]
    bu_install_str = " ".join(bu_install)

    if not has_uvx:
        ui.skip("uvx not available")
        return False

    if sysinfo.browser_use_chromium_installed():
        ui.ok("browser-use Chromium already installed")
        return True

    if sys.stdin.isatty() and ui.confirm(
        f"Install browser-use's Chromium now? Runs '{bu_install_str}', "
        "which may prompt for your sudo password."
    ):
        # Run directly, not through spin(): the underlying "playwright
        # install --with-deps" shells out to sudo apt-get on Linux, and a
        # spinner would hide that password prompt and hang silently.
        result = subprocess.run(bu_install, shell=_SHELL)
        if result.returncode == 0:
            ui.ok("browser-use Chromium installed")
            return True
        ui.warn(f"Chromium install failed - run '{bu_install_str}' manually later")
        return False

    ui.ok("Will register - see the one-time Chromium install noted below")
    return False


def _lightpanda_step(env: dict[str, str]) -> bool:
    ui.step("Lightpanda (fast local browser engine)")
    if sys.platform not in ("linux", "darwin"):
        ui.skip(f"Not supported on {sys.platform} without WSL (lightpanda has no native Windows build yet)")
        return False
    if env.get("SKIP_LIGHTPANDA") == "1":
        ui.skip("SKIP_LIGHTPANDA=1")
        return False
    if _install_tool("lightpanda", "https://pkg.lightpanda.io/install.sh", ""):
        return True
    ui.warn("lightpanda install failed - lightpanda MCP entry will be skipped")
    return False


def _bifrost_step(env: dict[str, str]) -> None:
    ui.step("Bifrost gateway")
    if env.get("SKIP_BIFROST") == "1":
        ui.skip("SKIP_BIFROST=1")
        return
    if bifrost.is_running():
        ui.ok("Already running on http://localhost:8080")
        return
    log_path = Path(tempfile.gettempdir()) / "bifrost.log"
    bifrost.start_background(log_path)
    ui.ok(f"Starting in background (log: {log_path}) - give it a few seconds")


def _summary_step(env: dict[str, str], bu_install_str: str) -> None:
    ui.step("Summary - what's left for you")
    ui.console.print(
        "1. Open http://localhost:8080, finish Bifrost onboarding, generate a virtual key.\n"
        '   claude mcp add --transport http bifrost http://localhost:8080/mcp '
        '--header "Authorization: Bearer <key>" --scope user\n'
        "2. In the Bifrost UI, add downstream servers you'd rather gateway than run direct\n"
        "   (command/args/env are in mcp-servers.json).\n\n"
        "Run ./setup.sh anytime to recheck what's installed.",
        style="blue",
    )

    warnings: list[str] = []

    if not (env.get("GITHUB_TOKEN") or env.get("GITHUB_PERSONAL_ACCESS_TOKEN")):
        warnings.append("- Set GITHUB_TOKEN and re-run to register the GitHub MCP server.")

    if env.get("HAS_UVX") != "true":
        warnings.append(
            "- Install uv/uvx (https://docs.astral.sh/uv/) and re-run to enable "
            "the browser-use MCP server."
        )
    elif env.get("BROWSER_USE_READY") != "true":
        warnings.append(
            f"- Run '{bu_install_str}' once before first using the browser-use "
            "MCP (installs Chromium, may prompt for sudo on Linux)."
        )

    if warnings:
        ui.step("Warnings")
        ui.console.print(escape("\n".join(warnings)), style="yellow")


def main() -> None:
    parser = argparse.ArgumentParser(prog="setup", description="Set up this Claude Code environment.")
    parser.add_argument(
        "--claude-md-only",
        action="store_true",
        help="skip installs and MCP registration; only generate/refresh this project's CLAUDE.md",
    )
    args = parser.parse_args()

    # Installers below drop binaries into these; prepended once up front so
    # anything installed during this run is findable in this same process.
    local_bin = str(Path.home() / ".local" / "bin")
    cargo_bin = str(Path.home() / ".cargo" / "bin")
    os.environ["PATH"] = os.pathsep.join([local_bin, cargo_bin, os.environ.get("PATH", "")])

    apply_env(load_env(REPO_ROOT / ".env"))
    project = _project_dir()

    if _choose_mode(args.claude_md_only) == MODE_CLAUDE_MD:
        _claude_md_step(project)
        return

    _git_hook_step()

    has_uvx = _required_tools_step()
    os.environ["HAS_UVX"] = "true" if has_uvx else "false"

    _codegraph_step(project)

    browser_use_ready = _browser_use_step(has_uvx)
    os.environ["BROWSER_USE_READY"] = "true" if browser_use_ready else "false"

    has_lightpanda = _lightpanda_step(dict(os.environ))
    os.environ["HAS_LIGHTPANDA"] = "true" if has_lightpanda else "false"

    _claude_md_step(project)

    ui.step("Registering MCP servers into ~/.claude.json")
    registered = mcp_config.merge_and_write(env=dict(os.environ))

    ui.step("Web/browser tool guidance in ~/.claude/CLAUDE.md")
    claudemd.ensure_web_tools_guidance(registered, env=dict(os.environ), ask=sys.stdin.isatty())

    _bifrost_step(dict(os.environ))

    bu_install_str = "uvx --python 3.12 browser-use[cli] install"
    _summary_step(dict(os.environ), bu_install_str)


if __name__ == "__main__":
    main()
