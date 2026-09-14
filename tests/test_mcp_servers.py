"""Integration suite: drives a real `claude -p` session against each MCP
server this repo registers, validating three independent layers so a
server that's registered but broken can't pass:

  1. connected  - the server's tools show up in the session's init event
  2. invoked    - the expected tool appears as a real tool_use in the
                  transcript (the model can't answer from memory instead)
  3. correct    - the final answer matches an expected pattern

Layer 2 is why every case runs with --strict-mcp-config plus a tool
allowlist and an explicit denylist of WebFetch/WebSearch/Bash/Read/etc:
without those the model can satisfy most of these prompts without
touching MCP at all, and the test would pass against a completely dead
server.

Marked `integration`: `uv run pytest` runs these by default alongside the
fast unit tests (one command runs everything), but `uv run pytest -m "not
integration"` gives a fast, no-network subset for routine local work.
Filter/parallelize/inspect with pytest's own mechanisms instead of a
bespoke CLI: `-k NAME` (was --filter), `-n N` (was --jobs, needs
pytest-xdist), `--model`/`--mcp-timeout` (conftest.py options, same
defaults as before), `--collect-only -q` (was --list).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from setup.mcpservers import REPO_ROOT

CHROME_PORT = 9223

# Built-ins that could answer these prompts without the MCP server under
# test. Denied so a pass can only come from the server actually working.
DENIED_TOOLS = "WebFetch,WebSearch,Bash,Read,Write,Edit,Glob,Grep,Task,NotebookEdit"


@dataclass(frozen=True)
class Case:
    name: str
    server: str
    tools: tuple[str, ...]  # allowlisted for the session
    must_call: tuple[str, ...]  # at least one of these must be invoked
    prompt: str
    expect: str  # regex the final answer must match
    why: str  # what a pass actually proves
    needs: str = ""  # prerequisite fixture key: "chrome" | "codegraph-index"
    resource: str = ""  # cases sharing a key never run concurrently (xdist_group)
    env: dict = field(default_factory=dict)  # extra env for the server entry


CASES = [
    Case(
        name="context7",
        server="context7",
        tools=("mcp__context7__resolve-library-id", "mcp__context7__query-docs"),
        must_call=("mcp__context7__resolve-library-id",),
        prompt=(
            "Use the resolve-library-id tool to find the Context7-compatible "
            "library ID for the Zod validation library. Reply with exactly one "
            "line, 'ID=<the library id>', and nothing else."
        ),
        # A Context7 ID is registry-assigned, so echoing it back proves a real lookup.
        expect=r"/colinhacks/zod",
        why="live documentation lookup returns a real registry ID",
    ),
    Case(
        name="firecrawl-scrape",
        server="firecrawl",
        tools=("mcp__firecrawl__firecrawl_scrape",),
        must_call=("mcp__firecrawl__firecrawl_scrape",),
        prompt=(
            "Use the firecrawl_scrape tool to scrape https://example.com . "
            "Reply with exactly one line, 'TITLE=<the page's main heading>', "
            "and nothing else."
        ),
        expect=r"Example Domain",
        why="self-hosted Firecrawl fetches and converts a live page",
    ),
    Case(
        name="firecrawl-js",
        server="firecrawl",
        tools=("mcp__firecrawl__firecrawl_scrape",),
        must_call=("mcp__firecrawl__firecrawl_scrape",),
        prompt=(
            "Use the firecrawl_scrape tool to scrape https://quotes.toscrape.com/js/ . "
            "That page builds its quote list with JavaScript. Count the quotes in "
            "the scraped content. Reply with exactly one line, 'COUNT=<number>', "
            "and nothing else."
        ),
        # The static HTML has zero rendered quotes - 10 only appears post-JS.
        expect=r"COUNT=\s*10\b",
        why="Firecrawl's headless browser executes JavaScript, not just raw HTML",
    ),
    Case(
        name="firecrawl-search",
        server="firecrawl",
        tools=("mcp__firecrawl__firecrawl_search",),
        must_call=("mcp__firecrawl__firecrawl_search",),
        prompt=(
            "Use the firecrawl_search tool to search the web for "
            "'Model Context Protocol specification'. Reply with exactly one line, "
            "'URL=<url of the single most relevant result>', and nothing else."
        ),
        expect=r"modelcontextprotocol",
        why="web search returns ranked live results",
    ),
    Case(
        name="github",
        server="github",
        tools=("mcp__github__get_file_contents",),
        must_call=("mcp__github__get_file_contents",),
        prompt=(
            "Use the get_file_contents tool to read the file 'README' from the "
            "GitHub repository octocat/Hello-World. Reply with exactly one line, "
            "'CONTENT=<the file's contents on one line>', and nothing else."
        ),
        # octocat/Hello-World's README has been "Hello World!" since 2011.
        expect=r"Hello World",
        why="the GitHub token authenticates and reads repository content",
    ),
    Case(
        name="codegraph",
        server="codegraph",
        tools=("mcp__codegraph__codegraph_explore",),
        must_call=("mcp__codegraph__codegraph_explore",),
        prompt=(
            "Use the codegraph_explore tool with projectPath "
            f"'{REPO_ROOT}' and query 'build_plan' to find where the build_plan "
            "function is defined. Reply with exactly one line, "
            "'FILE=<repo-relative path of the file defining it>', and nothing else."
        ),
        expect=r"mcpconfig\.py",
        why="the code graph index resolves a symbol to its defining file",
        needs="codegraph-index",
    ),
    Case(
        name="obsidian",
        server="obsidian",
        tools=("mcp__obsidian__library_stats",),
        must_call=("mcp__obsidian__library_stats",),
        # Read-only on purpose: never write into someone's real vault to prove it works.
        prompt=(
            "Use the library_stats tool to get statistics about the vault. Reply "
            "with exactly one line, 'NOTES=<the total number of notes>', and "
            "nothing else."
        ),
        expect=r"NOTES=\s*\d+",
        why="librarian-mcp reads the configured vault off disk",
    ),
    Case(
        name="browser-use",
        server="browser-use",
        tools=("mcp__browser-use__browser_exec",),
        must_call=("mcp__browser-use__browser_exec",),
        prompt=(
            "Use the browser_exec tool to run this Python in the browser harness:\n"
            "new_tab('https://quotes.toscrape.com/js/')\n"
            "wait_for_load()\n"
            "print(js(\"document.querySelectorAll('.quote').length\"))\n"
            "Then reply with exactly one line, 'COUNT=<the number printed>', "
            "and nothing else."
        ),
        expect=r"COUNT=\s*10\b",
        why="Chromium is driven over CDP and executes page JavaScript",
        needs="chrome",
        resource="browser",
        env={"BU_CDP_URL": f"http://127.0.0.1:{CHROME_PORT}"},
    ),
    Case(
        name="lightpanda",
        server="lightpanda",
        tools=("mcp__lightpanda__evaluate",),
        must_call=("mcp__lightpanda__evaluate",),
        prompt=(
            "Use the evaluate tool with url 'https://quotes.toscrape.com/js/' and "
            "script \"document.querySelectorAll('.quote').length\" to count the "
            "quotes on that JavaScript-rendered page. Reply with exactly one "
            "line, 'COUNT=<the number>', and nothing else."
        ),
        expect=r"COUNT=\s*10\b",
        why="Lightpanda's native MCP server drives its own engine directly, not via CDP",
        resource="browser",
    ),
]


def _params():
    for case in CASES:
        marks = [pytest.mark.xdist_group(name=case.resource)] if case.resource else []
        yield pytest.param(case, id=case.name, marks=marks)


@pytest.fixture(scope="session", autouse=True)
def _require_claude_cli():
    if not shutil.which("claude"):
        pytest.skip("claude CLI not found on PATH")


@pytest.mark.integration
@pytest.mark.parametrize("case", list(_params()))
def test_mcp_server(
    case: Case,
    registered_servers: dict,
    managed_servers: dict,
    model: str,
    mcp_timeout: int,
    request: pytest.FixtureRequest,
) -> None:
    if case.server not in registered_servers:
        if case.server not in managed_servers:
            pytest.skip("not a server this repo manages")
        pytest.skip("not registered in ~/.claude.json")

    if case.needs == "chrome":
        request.getfixturevalue("chrome_prereq")
    elif case.needs == "codegraph-index":
        request.getfixturevalue("codegraph_index")

    entry = registered_servers[case.server]
    server_entry = {**entry, "env": {**entry.get("env", {}), **case.env}} if case.env else entry

    with tempfile.TemporaryDirectory(prefix="mcp-test-") as tmp:
        config = Path(tmp) / "mcp.json"
        config.write_text(
            json.dumps({"mcpServers": {case.server: server_entry}}), encoding="utf-8"
        )
        cmd = [
            "claude",
            "-p",
            case.prompt,
            "--model",
            model,
            "--output-format",
            "stream-json",
            "--verbose",
            "--strict-mcp-config",
            "--mcp-config",
            str(config),
            "--allowedTools",
            ",".join(case.tools),
            "--disallowedTools",
            DENIED_TOOLS,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=mcp_timeout,
                cwd=tmp,  # no CLAUDE.md / repo context leaking into the answer
                shell=(sys.platform == "win32"),
            )
        except subprocess.TimeoutExpired:
            pytest.fail(f"timed out after {mcp_timeout}s")

    offered: list[str] = []
    invoked: list[str] = []
    tool_errors: list[str] = []
    answer = ""

    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            offered = [t for t in event.get("tools", []) if t.startswith("mcp__")]
        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    invoked.append(block.get("name", ""))
        elif kind == "user":
            for block in event.get("message", {}).get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                    tool_errors.append(str(block.get("content"))[:200])
        elif kind == "result":
            answer = str(event.get("result") or "")

    # Layer 1: did the server connect and publish its tools?
    if not any(t in offered for t in case.tools):
        hint = f"server exposed no tools (got {len(offered)})"
        if tool_errors:
            hint += f"; first error: {tool_errors[0]}"
        pytest.fail(hint)

    # Layer 2: was the tool actually called?
    if not any(t in invoked for t in case.must_call):
        called = ", ".join(sorted(set(invoked))) or "none"
        detail = f"expected {case.must_call[0]} to be called, but tools called were: {called}"
        if tool_errors:
            detail += f"; tool error: {tool_errors[0]}"
        pytest.fail(detail)

    # Layer 3: is the answer right?
    if not re.search(case.expect, answer, re.IGNORECASE):
        detail = f"answer did not match /{case.expect}/ (got: {answer[:300]!r})"
        if tool_errors:
            detail += f"; tool error: {tool_errors[0]}"
        pytest.fail(detail)
