"""Three-arm probe: same 8 Drizzle questions through Context7, Firecrawl live,
and the vault mirror - each as a fresh `claude -p` session locked to one arm's
MCP server, so no arm inherits another's answer.

Same technique as tests/test_mcp_servers.py. Records, per question per arm:
correct (fixed regex), tool calls, bytes returned by tools (the tokens-into-
context proxy), the session's own usage numbers, and wall-clock.

Run from the repo root (needs OBSIDIAN_VAULT_PATH exported, and the vault
must already hold the Drizzle 1.0-beta mirror - see results.md for the crawl
command):

    uv run python -m bench.docs_retrieval.threearm            # all three arms
    uv run python -m bench.docs_retrieval.threearm C-vault    # one arm

24 sonnet sessions, ~10 minutes, costs real tokens. Appends to results.jsonl.
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bench.harness import DENIED_BUILTINS, DENIED_WEB, bench_env, run_session

HERE = Path(__file__).parent
OUT = HERE / "results.jsonl"
MODEL = "sonnet"
TIMEOUT = 420
WORKERS = 3
DENIED = f"{DENIED_WEB},{DENIED_BUILTINS}"

ENV = bench_env()
VAULT = ENV["vault"]
FIRECRAWL_API_URL = ENV["firecrawl_api_url"]

SERVERS = {
    "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp@latest"]},
    "firecrawl": {
        "command": "npx",
        "args": ["-y", "firecrawl-mcp@3.23.7"],
        "env": {"FIRECRAWL_API_URL": FIRECRAWL_API_URL},
    },
    "obsidian": {"command": "librarian-mcp", "args": [VAULT]},
}

# MCP tools are deferred in `claude -p` (loaded via ToolSearch by name), and a
# fresh session has no idea the vault holds docs - it searched for "context7",
# "firecrawl", "web fetch" and gave up. That routing gap is a real finding, but
# it's not what this probe measures, so every arm gets the same one-line hint
# naming its tools.
ARMS = {
    "A-context7": ("context7", [
        "mcp__context7__resolve-library-id", "mcp__context7__query-docs",
    ], "Use the Context7 tools (resolve-library-id, then query-docs)."),
    "B-firecrawl": ("firecrawl", [
        "mcp__firecrawl__firecrawl_search", "mcp__firecrawl__firecrawl_developer_search",
        "mcp__firecrawl__firecrawl_scrape", "mcp__firecrawl__firecrawl_map",
    ], "Use the Firecrawl tools (firecrawl_search and/or firecrawl_scrape)."),
    "C-vault": ("obsidian", [
        "mcp__obsidian__library_search", "mcp__obsidian__library_read",
        "mcp__obsidian__library_list",
    ], "Use the library tools (library_search, then library_read) - a local documentation vault."),
}

# Correctness regexes were fixed in results.md before any arm ran.
QUESTIONS = [
    ("Q1", "In Drizzle ORM, how do I select only specific columns from a table instead of all of them?",
     r"select\(\s*\{"),
    ("Q2", "In Drizzle ORM, how do I do a LEFT JOIN, and what does the result shape look like?",
     r"leftJoin"),
    ("Q3", "In Drizzle ORM, how do I fetch a user together with all their posts in one query using the relational query API?",
     r"findMany[\s\S]*with\s*:"),
    ("Q4", "In Drizzle ORM, how do I run multiple writes inside a transaction, and how do I roll it back?",
     r"(?=[\s\S]*transaction\()(?=[\s\S]*rollback)"),
    ("Q5", "With Drizzle ORM, how do I generate SQL migration files from my schema using drizzle-kit?",
     r"drizzle-kit generate"),
    ("Q6", "In Drizzle ORM, how do I add a unique index on a column in my schema?",
     r"uniqueIndex|\.unique\("),
    ("Q7", "In Drizzle ORM, how do I do an upsert (insert, or update on conflict)?",
     r"onConflictDoUpdate"),
    ("Q8", "In Drizzle ORM, how do I define a Postgres table with a serial primary key and a timestamp column?",
     r"(?=[\s\S]*serial\()(?=[\s\S]*timestamp\()"),
]

PROMPT = (
    "{question}\n\n"
    "{hint} Look this up - do not answer from memory. "
    "Reply concisely with the exact API and a short code example."
)


def run_one(arm: str, qid: str, question: str, expect: str) -> dict:
    server, tools, hint = ARMS[arm]
    rec = run_session(
        PROMPT.format(question=question, hint=hint),
        {server: SERVERS[server]}, tools,
        denied=DENIED, model=MODEL, timeout=TIMEOUT,
    )
    calls = [c.replace("mcp__", "") for c in rec["calls"]]
    return {
        "arm": arm, "q": qid,
        "correct": bool(re.search(expect, rec["answer"])),
        **rec,
        "calls": calls,
        "mcp_calls": sum(1 for c in calls if c.startswith(server)),
    }


def main() -> None:
    if not Path(VAULT).is_dir():
        sys.exit("OBSIDIAN_VAULT_PATH is not a directory - export it first")
    arms = sys.argv[1:] or list(ARMS)
    jobs = [(arm, qid, q, exp) for arm in arms for qid, q, exp in QUESTIONS]
    print(f"{len(jobs)} sessions, {WORKERS} at a time, model={MODEL}", flush=True)
    with OUT.open("a") as out, ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for rec in pool.map(lambda j: run_one(*j), jobs):
            out.write(json.dumps(rec) + "\n"); out.flush()
            mark = "ok " if rec["correct"] else "BAD"
            print(f"{mark} {rec['arm']:12} {rec['q']}  calls={rec['round_trips']} (mcp {rec['mcp_calls']})  "
                  f"tool_bytes={rec['tool_bytes']:>7}  wall={rec['wall_s']:>5}s  "
                  f"{'TIMEOUT' if rec['timed_out'] else ''}", flush=True)


if __name__ == "__main__":
    main()
