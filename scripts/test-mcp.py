#!/usr/bin/env python3
"""Drives a real `claude -p` session against each MCP server this repo
registers and checks it actually works end-to-end.

Each case is validated in three independent layers, so a server that is
registered but broken can't pass:

  1. connected  - the server's tools show up in the session's init event
  2. invoked    - the expected tool appears as a real tool_use in the
                  transcript (the model can't answer from memory instead)
  3. correct    - the final answer matches an expected pattern

Layer 2 is why every case runs with --strict-mcp-config plus a tool
allowlist and an explicit denylist of WebFetch/WebSearch/Bash/Read: without
those the model can satisfy most of these prompts without touching MCP at
all, and the test would pass against a completely dead server.

Run: python3 scripts/test-mcp.py [--filter NAME] [--jobs N] [--list]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = REPO_ROOT / "mcp-servers.json"
CLAUDE_CONFIG = Path.home() / ".claude.json"

CHROME_PORT = 9223

# Built-ins that could answer these prompts without the MCP server under
# test. Denied so a pass can only come from the server actually working.
DENIED_TOOLS = "WebFetch,WebSearch,Bash,Read,Write,Edit,Glob,Grep,Task,NotebookEdit"

GREEN, GRAY, RED, YELLOW, BLUE, BOLD, RESET = (
    "\033[32m", "\033[90m", "\033[31m", "\033[33m", "\033[34m", "\033[1m", "\033[0m",
)


def paint(code: str, text: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"{code}{text}{RESET}"


@dataclass(frozen=True)
class Case:
    name: str
    server: str
    tools: tuple[str, ...]          # allowlisted for the session
    must_call: tuple[str, ...]      # at least one of these must be invoked
    prompt: str
    expect: str                     # regex the final answer must match
    why: str                        # what a pass actually proves
    needs: str = ""                 # prerequisite key, see PREREQS
    resource: str = ""              # cases sharing a key never run concurrently
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
        expect=r"merge-mcp-config\.py",
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


# --------------------------------------------------------------------------
# Prerequisites: browsers these cases drive. Started only if not already up,
# and only ones we started get stopped again.
# --------------------------------------------------------------------------

def cdp_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
            return bool(json.loads(r.read()).get("webSocketDebuggerUrl"))
    except Exception:
        return False


def find_chromium() -> str | None:
    for pattern in ("chromium-*/chrome-linux*/chrome", "chromium-*/chrome-*/Chromium"):
        hits = sorted((Path.home() / ".cache" / "ms-playwright").glob(pattern))
        if hits:
            return str(hits[-1])
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def start_chrome() -> tuple[subprocess.Popen | None, str]:
    if cdp_alive(CHROME_PORT):
        return None, ""
    exe = find_chromium()
    if not exe:
        return None, "no Chromium-family browser found (run: uvx --python 3.12 'browser-use[cli]' install)"
    profile = tempfile.mkdtemp(prefix="mcp-test-chrome-")
    proc = subprocess.Popen(
        [exe, "--headless=new", f"--remote-debugging-port={CHROME_PORT}",
         "--no-sandbox", "--disable-gpu", f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return (proc, "") if wait_for(CHROME_PORT) else (proc, "Chromium did not expose a CDP port")


def wait_for(port: int, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cdp_alive(port):
            return True
        time.sleep(0.4)
    return False


PREREQS = {
    "chrome": start_chrome,
    "codegraph-index": lambda: (
        (None, "") if (REPO_ROOT / ".codegraph").is_dir()
        else (None, "no .codegraph index here (run: codegraph init)")
    ),
}


# --------------------------------------------------------------------------
# Running one case
# --------------------------------------------------------------------------

@dataclass
class Result:
    case: Case
    status: str      # pass | fail | skip
    detail: str
    seconds: float = 0.0
    answer: str = ""


def run_case(case: Case, entry: dict, model: str, timeout: int) -> Result:
    server_entry = {**entry, "env": {**entry.get("env", {}), **case.env}} if case.env else entry
    started = time.time()

    with tempfile.TemporaryDirectory(prefix="mcp-test-") as tmp:
        config = Path(tmp) / "mcp.json"
        config.write_text(json.dumps({"mcpServers": {case.server: server_entry}}), encoding="utf-8")
        cmd = [
            "claude", "-p", case.prompt,
            "--model", model,
            "--output-format", "stream-json", "--verbose",
            "--strict-mcp-config", "--mcp-config", str(config),
            "--allowedTools", ",".join(case.tools),
            "--disallowedTools", DENIED_TOOLS,
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                cwd=tmp,  # no CLAUDE.md / repo context leaking into the answer
            )
        except subprocess.TimeoutExpired:
            return Result(case, "fail", f"timed out after {timeout}s", time.time() - started)

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

    elapsed = time.time() - started

    # Layer 1: did the server connect and publish its tools?
    if not any(t in offered for t in case.tools):
        hint = f"server exposed no tools (got {len(offered)})"
        if tool_errors:
            hint += f"; first error: {tool_errors[0]}"
        return Result(case, "fail", hint, elapsed, answer)

    # Layer 2: was the tool actually called?
    if not any(t in invoked for t in case.must_call):
        called = ", ".join(sorted(set(invoked))) or "none"
        detail = f"expected {case.must_call[0]} to be called, but tools called were: {called}"
        if tool_errors:
            detail += f"; tool error: {tool_errors[0]}"
        return Result(case, "fail", detail, elapsed, answer)

    # Layer 3: is the answer right?
    if not re.search(case.expect, answer, re.IGNORECASE):
        detail = f"answer did not match /{case.expect}/"
        if tool_errors:
            detail += f"; tool error: {tool_errors[0]}"
        return Result(case, "fail", detail, elapsed, answer)

    return Result(case, "pass", case.why, elapsed, answer)


# --------------------------------------------------------------------------

def load_registered() -> dict:
    if not CLAUDE_CONFIG.exists():
        return {}
    try:
        return json.loads(CLAUDE_CONFIG.read_text(encoding="utf-8")).get("mcpServers", {}) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--filter", default="", help="only run cases whose name contains this")
    parser.add_argument("--jobs", type=int, default=4, help="cases to run concurrently (default: 4)")
    parser.add_argument("--model", default="sonnet", help="model alias to test with (default: sonnet)")
    parser.add_argument("--timeout", type=int, default=300, help="per-case timeout in seconds")
    parser.add_argument("--list", action="store_true", help="list cases and exit")
    args = parser.parse_args()

    cases = [c for c in CASES if args.filter in c.name]
    if args.list:
        for c in cases:
            print(f"  {c.name:24s} {c.server:22s} {c.why}")
        return 0
    if not cases:
        print(f"No cases match --filter {args.filter!r}")
        return 2
    if not shutil.which("claude"):
        print(paint(RED, "  x claude CLI not found on PATH"))
        return 2

    registered = load_registered()
    managed = [c for c in json.loads(SOURCE_PATH.read_text(encoding="utf-8"))["mcpServers"]]

    print(paint(BOLD, f"\nTesting {len(cases)} case(s) against model '{args.model}'\n"))

    # Skip anything not registered, and start whatever prerequisites are needed.
    results: list[Result] = []
    runnable: list[Case] = []
    started: list[subprocess.Popen] = []
    prereq_failures: dict[str, str] = {}

    for case in cases:
        if case.server not in registered:
            why = "not registered in ~/.claude.json"
            if case.server not in managed:
                why = "not a server this repo manages"
            results.append(Result(case, "skip", why))
            continue
        if case.needs:
            if case.needs not in prereq_failures:
                proc, problem = PREREQS[case.needs]()
                if proc:
                    started.append(proc)
                prereq_failures[case.needs] = problem
            if prereq_failures[case.needs]:
                results.append(Result(case, "skip", prereq_failures[case.needs]))
                continue
        runnable.append(case)

    locks: dict[str, threading.Lock] = {}
    print_lock = threading.Lock()

    def execute(case: Case) -> Result:
        lock = locks.setdefault(case.resource, threading.Lock()) if case.resource else None
        if lock:
            with lock:
                result = run_case(case, registered[case.server], args.model, args.timeout)
        else:
            result = run_case(case, registered[case.server], args.model, args.timeout)
        with print_lock:
            report(result)
        return result

    try:
        if runnable:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
                results.extend(pool.map(execute, runnable))
    finally:
        for proc in started:
            proc.terminate()

    for result in results:
        if result.status == "skip":
            report(result)

    return summarize(results)


def report(result: Result) -> None:
    took = paint(GRAY, f"({result.seconds:.0f}s)") if result.seconds else ""
    if result.status == "pass":
        print(f"  {paint(GREEN, 'PASS')} {result.case.name:24s} {took} {paint(GRAY, result.detail)}")
    elif result.status == "skip":
        print(f"  {paint(GRAY, 'SKIP')} {result.case.name:24s} {paint(GRAY, result.detail)}")
    else:
        print(f"  {paint(RED, 'FAIL')} {result.case.name:24s} {took} {paint(YELLOW, result.detail)}")
        if result.answer:
            print(paint(GRAY, f"         answer: {result.answer[:300]}"))


def summarize(results: list[Result]) -> int:
    passed = [r for r in results if r.status == "pass"]
    failed = [r for r in results if r.status == "fail"]
    skipped = [r for r in results if r.status == "skip"]

    print(paint(BLUE, f"\n  {len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped\n"))
    if failed:
        print(paint(RED, "  Failing servers:"))
        for r in failed:
            print(paint(RED, f"    - {r.case.name}: {r.detail}"))
        print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
