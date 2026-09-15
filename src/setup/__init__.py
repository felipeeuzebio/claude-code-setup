"""One-shot setup for this Claude Code environment - Linux/WSL2/macOS/native
Windows alike. Installs what it can, registers what it can into
~/.claude.json, and prints exactly what's left to do by hand.

This is the single orchestration spine that used to be duplicated between
setup.sh and setup.ps1: one codebase, branching on `sys.platform` only
where behavior genuinely differs (Lightpanda: Linux/Darwin only; the
codegraph/librarian-mcp installer one-liner: curl|bash vs irm|iex).

Optional config via env vars or a repo-root .env file (see .env.example):
  GITHUB_TOKEN, OBSIDIAN_VAULT_PATH,
  SKIP_FIRECRAWL=1, SKIP_BIFROST=1, SKIP_LIGHTPANDA=1
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.markup import escape

from setup import bifrost, claudemd, firecrawl, mcpconfig, sysinfo, ui
from setup.envfile import apply_env, load_env
from setup.mcpservers import REPO_ROOT

_SHELL = sys.platform == "win32"


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


def _required_tools_step() -> dict[str, bool]:
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

    has_docker = sysinfo.docker_ready()
    if has_docker:
        ui.ok_ver("docker", sysinfo.docker_version())
    elif shutil.which("docker"):
        ui.warn("docker found but not running - start Docker Desktop")
    else:
        ui.warn("docker not available - Firecrawl self-host will be skipped (see AGENTS.md)")

    has_uvx, uvx_version = sysinfo.check_tool("uvx")
    if has_uvx:
        ui.ok_ver("uvx", uvx_version)
    else:
        ui.warn(
            "uvx not available - browser-use (self-hosted) will be skipped "
            "(install: https://docs.astral.sh/uv/)"
        )

    return {"docker": has_docker, "uvx": has_uvx}


def _codegraph_step() -> None:
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

    # init builds an index from scratch, sync refreshes the existing one.
    cg_action = "sync" if (REPO_ROOT / ".codegraph").is_dir() else "init"
    if not sys.stdin.isatty():
        ui.console.print(
            f"  Run 'codegraph {cg_action}' in this repo (or any project) "
            "whenever you want to build/refresh its index."
        )
    elif ui.confirm(f"Run 'codegraph {cg_action}' for this repo now?"):
        ui.spin(
            f"Running codegraph {cg_action}...",
            lambda: subprocess.run(["codegraph", cg_action], shell=_SHELL),
        )
        ui.ok(f"codegraph {cg_action} complete")
    else:
        ui.skip(f"Skipped - run 'codegraph {cg_action}' in this repo anytime")


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


def _librarian_mcp_step(env: dict[str, str]) -> None:
    ui.step("librarian-mcp (Obsidian)")
    unix_url = "https://github.com/ngmeyer/librarian-mcp/releases/latest/download/librarian-mcp-installer.sh"
    windows_url = "https://github.com/ngmeyer/librarian-mcp/releases/latest/download/librarian-mcp-installer.ps1"

    if not _install_tool("librarian-mcp", unix_url, windows_url):
        ui.warn("librarian-mcp install failed - obsidian MCP entry will be skipped")
        return

    vault_path = env.get("OBSIDIAN_VAULT_PATH", "")
    if not vault_path:
        ui.warn("OBSIDIAN_VAULT_PATH not set - obsidian MCP entry will be skipped")
    elif not Path(vault_path).is_dir():
        ui.warn(
            f"OBSIDIAN_VAULT_PATH is not an existing directory: {vault_path} - "
            "obsidian MCP entry will be skipped (under WSL2, a Windows-side "
            "vault needs /mnt/c/... not C:\\...)"
        )


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


def _firecrawl_step(has_docker: bool, env: dict[str, str]) -> None:
    ui.step("Firecrawl (self-hosted web scraping)")
    if not has_docker:
        ui.skip("docker unavailable")
        return
    if env.get("SKIP_FIRECRAWL") == "1":
        ui.skip("SKIP_FIRECRAWL=1")
        return
    already_running = firecrawl.is_running()
    result = ui.spin("Bringing up self-hosted Firecrawl...", firecrawl.bring_up)
    if not result.ok:
        ui.warn("Firecrawl bring-up failed - see output above")
        ui.console.print(escape(result.log))
        return
    ui.ok("Firecrawl already running" if already_running else "Firecrawl is up")


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
    issues: list[str] = []

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

    vault_path = env.get("OBSIDIAN_VAULT_PATH", "")
    if not vault_path:
        warnings.append(
            "- Set OBSIDIAN_VAULT_PATH and re-run to register the Obsidian "
            "(librarian-mcp) server."
        )
    elif not Path(vault_path).is_dir():
        issues.append(
            f"- OBSIDIAN_VAULT_PATH ({vault_path}) is not an existing directory - "
            "fix it and re-run to register the Obsidian (librarian-mcp) server."
        )

    if issues or warnings:
        ui.step("Warnings & issues")
        if issues:
            ui.console.print(escape("\n".join(issues)), style="red")
        if warnings:
            ui.console.print(escape("\n".join(warnings)), style="yellow")


def main() -> None:
    # Installers below drop binaries into these; prepended once up front so
    # anything installed during this run is findable in this same process.
    local_bin = str(Path.home() / ".local" / "bin")
    cargo_bin = str(Path.home() / ".cargo" / "bin")
    os.environ["PATH"] = os.pathsep.join([local_bin, cargo_bin, os.environ.get("PATH", "")])

    apply_env(load_env(REPO_ROOT / ".env"))

    _git_hook_step()

    tool_status = _required_tools_step()
    has_docker = tool_status["docker"]
    has_uvx = tool_status["uvx"]
    os.environ["HAS_UVX"] = "true" if has_uvx else "false"

    _codegraph_step()

    browser_use_ready = _browser_use_step(has_uvx)
    os.environ["BROWSER_USE_READY"] = "true" if browser_use_ready else "false"

    _librarian_mcp_step(dict(os.environ))

    has_lightpanda = _lightpanda_step(dict(os.environ))
    os.environ["HAS_LIGHTPANDA"] = "true" if has_lightpanda else "false"

    ui.step("CLAUDE.md for this repo")
    claudemd.ensure_claude_md()

    ui.step("Registering MCP servers into ~/.claude.json")
    mcpconfig.merge_and_write(env=dict(os.environ))

    _firecrawl_step(has_docker, dict(os.environ))
    _bifrost_step(dict(os.environ))

    bu_install_str = "uvx --python 3.12 browser-use[cli] install"
    _summary_step(dict(os.environ), bu_install_str)


if __name__ == "__main__":
    main()
