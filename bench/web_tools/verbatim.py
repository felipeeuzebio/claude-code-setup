"""Verbatim-content follow-up to webtools.py: can each arm reproduce exact
text from a page - a long quote, an install command, a code line, a setting
buried in a 420 KB reference page - or does it paraphrase?

This is the gap webtools.py left open. Built-in WebFetch returns a side-
model *summary* of the page, so it can be right about "who wrote this" and
wrong about "what exactly does line 3 say". The global WEB_TOOLS block now
routes single-page reads to WebFetch first; this checks what that costs.

Same arms and runner as webtools.py, matched case-sensitively. Run from the
repo root (Firecrawl arm needs an instance at FIRECRAWL_API_URL):

    uv run python -m bench.web_tools.verbatim
    uv run python -m bench.web_tools.verbatim builtin lightpanda

12 sonnet sessions. Appends to verbatim.jsonl.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bench.web_tools.webtools import MODEL, WORKERS, run_one

OUT = Path(__file__).parent / "verbatim.jsonl"
ARMS = ["builtin", "firecrawl", "lightpanda"]

# (id, prompt, case-sensitive regex). Expected strings were read off the
# live pages with curl on 2026-09-16 - see results.md.
TASKS = [
    ("V1",
     "Give the full text of the first quote on https://quotes.toscrape.com/page/3/ "
     "exactly as written on the page, word for word.",
     r"so intimate that your hand upon my chest is my hand, so intimate that when I fall asleep your eyes close"),
    ("V2",
     "What is the exact `cargo install` command given in the README at "
     "https://github.com/ngmeyer/librarian-mcp ? Quote it verbatim.",
     r"cargo install --git https://github\.com/ngmeyer/librarian-mcp"),
    ("V3",
     "On https://orm.drizzle.team/docs/transactions , quote verbatim the first "
     "`await tx.update(...)` line from the first code example on the page.",
     r"update\(accounts\)\.set\(\{ balance: sql`\$\{accounts\.balance\} - 100\.00` \}\)\.where\(eq\(users\.name, 'Dan'\)\)"),
    ("V4",
     "On https://docs.astral.sh/uv/reference/settings/ , find the `python-preference` "
     "setting. Reply with its default value and its four possible values, each quoted "
     "exactly as the page writes them.",
     r'(?=[\s\S]*"only-managed")(?=[\s\S]*"managed")(?=[\s\S]*"system")(?=[\s\S]*"only-system")'),
]


def main() -> None:
    arms = sys.argv[1:] or ARMS
    jobs = [(arm, tid, task, exp) for arm in arms for tid, task, exp in TASKS]
    print(f"{len(jobs)} sessions, {WORKERS} at a time, model={MODEL}", flush=True)
    with OUT.open("a") as out, ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for rec in pool.map(lambda j: run_one(*j, flags=0), jobs):
            out.write(json.dumps(rec) + "\n"); out.flush()
            mark = "ok " if rec["correct"] else "BAD"
            print(f"{mark} {rec['arm']:12} {rec['t']}  calls={rec['round_trips']} (arm {rec['arm_calls']})  "
                  f"tool_bytes={rec['tool_bytes']:>7}  wall={rec['wall_s']:>5}s  errors={rec['tool_errors']}  "
                  f"{'TIMEOUT' if rec['timed_out'] else ''}", flush=True)


if __name__ == "__main__":
    main()
