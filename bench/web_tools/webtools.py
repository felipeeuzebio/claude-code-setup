"""Web bench: the registered web/browser MCP servers (Firecrawl, Lightpanda,
browser-use) against Claude Code's built-in WebSearch/WebFetch, on the tasks
the global WEB_TOOLS block routes between them - search, a static page, a
JS-rendered page, and a multi-page "follow Next" crawl.

Each task x arm is a fresh `claude -p` session locked to that arm's tools.
Recorded per session: correct (fixed regex, and at least one tool call - an
answer from memory doesn't count), tool calls, bytes returned by tools (the
tokens-into-context proxy), wall-clock.

Run from the repo root (needs self-hosted Firecrawl up at
FIRECRAWL_API_URL; `lightpanda` on PATH; a Chromium for browser-use - the
bench starts a headless one on CHROME_PORT if none is listening):

    uv run python -m bench.web_tools.webtools              # all arms
    uv run python -m bench.web_tools.webtools builtin      # one arm

~20 sonnet sessions, costs real tokens. Appends to results.jsonl.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bench.harness import DENIED_BUILTINS, DENIED_WEB, bench_env, run_session

HERE = Path(__file__).parent
OUT = HERE / "results.jsonl"
MODEL = "sonnet"
TIMEOUT = 420
WORKERS = 3
CHROME_PORT = 9223  # same port tests/conftest.py uses

ENV = bench_env()

SERVERS = {
    "firecrawl": {
        "command": "npx",
        "args": ["-y", "firecrawl-mcp@3.23.7"],
        "env": {"FIRECRAWL_API_URL": ENV["firecrawl_api_url"]},
    },
    "lightpanda": {"command": "lightpanda", "args": ["mcp"]},
    "browser-use": {
        "command": "uvx",
        "args": ["--python", "3.12", "browser-use[cli]", "--cli-mcp"],
        "env": {"BU_CDP_URL": f"http://127.0.0.1:{CHROME_PORT}"},
    },
}

# arm -> (server or None for built-ins, allowed tools, prefix that counts as
# "used the arm's tool", symmetric hint). MCP tools are deferred in `claude -p`
# and a fresh session doesn't know which server does what, so every arm gets
# one line naming its tools - same reasoning as docs_retrieval/threearm.py.
ARMS = {
    "builtin": (None, ["WebSearch", "WebFetch"], ("WebSearch", "WebFetch"),
                "Use the built-in WebSearch and WebFetch tools."),
    "firecrawl": ("firecrawl", [
        "mcp__firecrawl__firecrawl_search", "mcp__firecrawl__firecrawl_scrape",
        "mcp__firecrawl__firecrawl_map", "mcp__firecrawl__firecrawl_crawl",
        "mcp__firecrawl__firecrawl_check_crawl_status",
    ], ("mcp__firecrawl__",),
        "Use the Firecrawl tools (firecrawl_search, firecrawl_scrape, firecrawl_map, firecrawl_crawl)."),
    "lightpanda": ("lightpanda", [
        "mcp__lightpanda__goto", "mcp__lightpanda__markdown", "mcp__lightpanda__tree",
        "mcp__lightpanda__extract", "mcp__lightpanda__evaluate", "mcp__lightpanda__links",
        "mcp__lightpanda__findElement", "mcp__lightpanda__click", "mcp__lightpanda__getUrl",
        "mcp__lightpanda__waitForSelector", "mcp__lightpanda__html",
    ], ("mcp__lightpanda__",),
        "Use the Lightpanda browser tools (markdown, goto, tree, extract, evaluate, links)."),
    "browser-use": ("browser-use", ["mcp__browser-use__browser_exec"], ("mcp__browser-use__",),
                    "Use the browser_exec tool (browser-use harness: new_tab(url), "
                    "wait_for_load(), js(...), goto_url(url))."),
}

# (id, kind, prompt, regex). Search tasks only run on arms that can search.
# Expected values were checked by hand against the live pages on 2026-09-16.
TASKS = [
    ("T1", "search",
     "Find the URL of the official Model Context Protocol specification.",
     r"modelcontextprotocol\.io"),
    ("T2", "search",
     "Find the GitHub repository (owner/name) of the librarian-mcp Obsidian MCP server.",
     r"ngmeyer/librarian-mcp"),
    ("T3", "fetch",
     "What is the main heading (h1) of https://example.com ?",
     r"Example Domain"),
    ("T4", "fetch-js",
     "How many quotes are listed on https://quotes.toscrape.com/js/ ? That page builds "
     "its quote list with JavaScript. Reply COUNT=<number>.",
     r"COUNT=\s*10\b"),
    ("T5", "fetch",
     "Who is the author of the first quote on https://quotes.toscrape.com/page/2/ ?",
     r"Marilyn Monroe"),
    ("T6", "crawl",
     "Starting from https://quotes.toscrape.com/ and following the 'Next' links, what is "
     "the URL of the last page - the one with no Next link? Reply with the URL.",
     r"page/10"),
]
SEARCH_ARMS = ("builtin", "firecrawl")

PROMPT = (
    "{task}\n\n"
    "{hint} Look this up with the tools - do not answer from memory. "
    "Reply concisely."
)


def _cdp_alive() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CHROME_PORT}/json/version", timeout=2) as r:
            return bool(json.loads(r.read()).get("webSocketDebuggerUrl"))
    except OSError:
        return False


def _find_chromium() -> str | None:
    for pattern in ("chromium-*/chrome-linux*/chrome", "chromium-*/chrome-*/Chromium"):
        hits = sorted((Path.home() / ".cache" / "ms-playwright").glob(pattern))
        if hits:
            return str(hits[-1])
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome", "msedge"):
        if found := shutil.which(name):
            return found
    return None


def ensure_chrome() -> subprocess.Popen | None:
    """Headless Chromium on CHROME_PORT for browser-use; returns the process
    if this call started it (caller terminates), None if one was already up."""
    if _cdp_alive():
        return None
    exe = _find_chromium()
    if not exe:
        sys.exit("no Chromium found for browser-use (run: uvx --python 3.12 'browser-use[cli]' install)")
    profile = tempfile.mkdtemp(prefix="bench-chrome-")
    proc = subprocess.Popen(
        [exe, "--headless=new", f"--remote-debugging-port={CHROME_PORT}", "--no-sandbox",
         "--disable-gpu", f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 25
    while time.time() < deadline and not _cdp_alive():
        time.sleep(0.4)
    if not _cdp_alive():
        proc.terminate()
        sys.exit("Chromium did not expose a CDP port")
    return proc


def run_one(arm: str, tid: str, task: str, expect: str, flags: int = re.IGNORECASE) -> dict:
    server, tools, prefixes, hint = ARMS[arm]
    servers = {server: SERVERS[server]} if server else {}
    denied = DENIED_BUILTINS if arm == "builtin" else f"{DENIED_WEB},{DENIED_BUILTINS}"
    rec = run_session(PROMPT.format(task=task, hint=hint), servers, tools,
                      denied=denied, model=MODEL, timeout=TIMEOUT)
    arm_calls = sum(1 for c in rec["calls"] if c.startswith(prefixes))
    return {
        "arm": arm, "t": tid,
        "correct": bool(re.search(expect, rec["answer"], flags)) and arm_calls > 0,
        **rec,
        "calls": [c.replace("mcp__", "") for c in rec["calls"]],
        "arm_calls": arm_calls,
    }


def main() -> None:
    arms = sys.argv[1:] or list(ARMS)
    chrome = ensure_chrome() if "browser-use" in arms else None
    try:
        with OUT.open("a") as out:
            for arm in arms:
                jobs = [(arm, tid, task, exp) for tid, kind, task, exp in TASKS
                        if kind != "search" or arm in SEARCH_ARMS]
                # browser-use sessions share the one Chrome on CHROME_PORT.
                workers = 1 if arm == "browser-use" else WORKERS
                print(f"{arm}: {len(jobs)} sessions, {workers} at a time, model={MODEL}", flush=True)
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    for rec in pool.map(lambda j: run_one(*j), jobs):
                        out.write(json.dumps(rec) + "\n"); out.flush()
                        mark = "ok " if rec["correct"] else "BAD"
                        print(f"{mark} {rec['arm']:12} {rec['t']}  calls={rec['round_trips']} "
                              f"(arm {rec['arm_calls']})  tool_bytes={rec['tool_bytes']:>7}  "
                              f"wall={rec['wall_s']:>5}s  errors={rec['tool_errors']}  "
                              f"{'TIMEOUT' if rec['timed_out'] else ''}", flush=True)
    finally:
        if chrome:
            chrome.terminate()


if __name__ == "__main__":
    main()
