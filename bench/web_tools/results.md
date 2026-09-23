# Web tools: Firecrawl, Lightpanda and browser-use vs built-in WebSearch/WebFetch

Date: 2026-09-16. `setup` writes a global `WEB_TOOLS` block into
`~/.claude/CLAUDE.md` that tells Claude to prefer the registered MCP servers
over the built-in WebSearch/WebFetch. This bench checks whether that's right
for the kinds of task the block routes between them. The harness is
`webtools.py`, using the same `claude -p` technique as `docs_retrieval/`:
model sonnet, one arm's tools per session, everything else denied.

## Arms

| Arm | Tools allowed | Runs the search tasks? |
|---|---|---|
| Built-in WebSearch/WebFetch | `WebSearch`, `WebFetch` (no MCP servers at all) | yes |
| Firecrawl | `firecrawl_search`, `firecrawl_scrape`, `firecrawl_map`, `firecrawl_crawl` (self-hosted at `FIRECRAWL_API_URL`) | yes |
| Lightpanda | `markdown`, `goto`, `tree`, `extract`, `evaluate`, `links`, ... (native `lightpanda mcp`) | no (no search tool) |
| browser-use | `browser_exec` against a headless Chromium on port 9223 | no (no search tool) |

## Tasks

| ID | Kind | Task | Expected answer |
|---|---|---|---|
| T1 | search | URL of the official Model Context Protocol specification | `modelcontextprotocol.io` |
| T2 | search | GitHub owner/name of the librarian-mcp Obsidian MCP server | `ngmeyer/librarian-mcp` |
| T3 | static fetch | The h1 of https://example.com | `Example Domain` |
| T4 | JS-rendered fetch | Number of quotes on https://quotes.toscrape.com/js/ (list is built client-side) | `COUNT=10` |
| T5 | static fetch | Author of the first quote on https://quotes.toscrape.com/page/2/ | `Marilyn Monroe` |
| T6 | crawl | Follow "Next" from https://quotes.toscrape.com/ to the last page | `/page/10/` |

A session counts as correct only if the regex matches and the arm's own tool
was called at least once, so an answer from memory scores 0. Every session
below did call its tool. 20 sessions in all (6 + 6 + 4 + 4).

## Correctness

| Task | Built-in WebSearch/WebFetch | Firecrawl | Lightpanda | browser-use |
|---|---|---|---|---|
| T1 | yes | yes | — | — |
| T2 | yes | no (other repo) | — | — |
| T3 | yes | yes | yes | yes |
| T4 | **no** (regex passed, inferred) | yes | yes | yes |
| T5 | yes | yes | yes | yes |
| T6 | yes | yes | yes | yes |
| **Verified correct (T2 excluded)** | **4/5** | **5/5** | **4/4** | **4/4** |

Two scoring caveats, both my fault as the task author, not the tools':

- T4 on the built-in arm is a false regex pass. The answer contains
  `COUNT=10`, but in the same breath the model said "WebFetch can't execute
  JavaScript, so it can't directly confirm the JS-rendered count", and it
  inferred 10 from the non-JS page after 6 WebFetch/WebSearch calls and 51 s.
  T4 measures whether an arm can see a JS-rendered page, so this is a
  failure, and the table scores it as one.
- T2 is inconclusive. Two unrelated projects are named `librarian-mcp`. The
  built-in arm found both and asked which one was meant; Firecrawl returned
  the other one. The task was underspecified, so T2 is left out of the
  totals.

There was also a design flaw: T6 did not measure crawling.
quotes.toscrape.com is a well-known scraping sandbox, and every arm jumped
straight to `/page/10/` and checked that it had no Next link. That took one
call for Firecrawl and Lightpanda, and three WebFetch calls for built-in
(pages 1, 10 and 11). A real multi-page test needs a site the model has
never seen.

## Tool output per session, bytes

The bytes that every tool result put into the session, as a proxy for tokens
into context (~4 bytes per token). Bold marks the cheapest arm on each task.

| Task | Built-in WebSearch/WebFetch | Firecrawl | Lightpanda | browser-use |
|---|---|---|---|---|
| T1 | **2,032** | 2,787 | — | — |
| T2 | 4,688 | **2,323** | — | — |
| T3 | 53 | 624 | 169 | **15** |
| T4 | 6,684 | 2,059 | 3,322 | **3** |
| T5 | 184 | 7,510 | 1,041 | **15** |
| T6 | **340** | 2,780 | 3,755 | 748 |
| **Median** | **1,186** | **2,552** | **2,182** | **15** |

The built-in and browser-use numbers are small because `WebFetch` returns a
side-model summary of the page (53 bytes for example.com), and `browser_exec`
returns only what the generated Python `print`s. Firecrawl and Lightpanda
return the page itself as markdown. For WebFetch, cheap also means lossy.
That's fine for a heading or a name; this run didn't test verbatim code or
config values.

Bytes in are only part of the bill, so the tables below come from the
session's own `usage` in the `result` event. Output tokens are what Claude
wrote, and that includes the Python each `browser_exec` call carries in its
input, which the bytes table can't see. Cached input tokens are the system
prompt, tool schemas and global CLAUDE.md, re-read on every turn (~100k per
turn here).

### Output tokens per session

| Task | Built-in WebSearch/WebFetch | Firecrawl | Lightpanda | browser-use |
|---|---|---|---|---|
| T1 | **343** | 360 | — | — |
| T2 | 810 | **269** | — | — |
| T3 | **181** | 249 | 183 | 277 |
| T4 | 2,268 | 260 | 298 | **233** |
| T5 | **224** | 238 | 343 | 276 |
| T6 | 668 | 537 | **360** | 390 |
| **Median** | **506** | **264** | **320** | **276** |

### Cached input tokens per session (≈ turns × ~100k)

| Task | Built-in WebSearch/WebFetch | Firecrawl | Lightpanda | browser-use |
|---|---|---|---|---|
| T1 | **103k** | 105k | — | — |
| T2 | 149k | **105k** | — | — |
| T3 | **102k** | 104k | 104k | 103k |
| T4 | 333k | 104k | 152k | **103k** |
| T5 | **102k** | 104k | 152k | 103k |
| T6 | 191k | 105k | 105k | **103k** |
| **Median** | **126k** | **105k** | **128k** | **103k** |

Two things stand out. browser-use's Python is short: its output tokens are in
line with Lightpanda's and Firecrawl's, so its 3-15 B results really are
cheap. And turn count drives the token total. Built-in T4's six calls re-read
333k cached tokens, against ~104k for any arm that got there in one call. A
few KB of tool output either way is noise next to one extra turn.

## Session wall-clock, s

The whole `claude -p` session, startup included. Bold marks the fastest arm
on each task. browser-use ran one session at a time because they all share
one Chromium; the other arms ran three in parallel, which may inflate their
times slightly.

| Task | Built-in WebSearch/WebFetch | Firecrawl | Lightpanda | browser-use |
|---|---|---|---|---|
| T1 | **13.3** | 19.2 | — | — |
| T2 | 30.5 | **15.5** | — | — |
| T3 | **8.5** | 14.7 | 9.0 | 14.8 |
| T4 | 50.9 | 15.8 | 12.1 | **10.3** |
| T5 | **9.0** | 10.6 | 12.1 | 13.4 |
| T6 | 17.7 | 13.9 | **9.3** | 18.2 |
| **Median** | **15.5** | **15.1** | **10.7** | **14.1** |

## Tool calls per session (the arm's own tools, excluding ToolSearch)

| Task | Built-in WebSearch/WebFetch | Firecrawl | Lightpanda | browser-use |
|---|---|---|---|---|
| T1 | **1** | **1** | — | — |
| T2 | 3 | **1** | — | — |
| T3 | **1** | **1** | **1** | **1** |
| T4 | 6 | **1** | 2 | **1** |
| T5 | **1** | **1** | 2 | **1** |
| T6 | 3 | **1** | **1** | **1** |
| **Median** | **2** | **1** | **1.5** | **1** |

## Reading it

- Static page (T3, T5): built-in WebFetch is both faster and cheaper, at
  8.5-9 s and under 200 bytes against Firecrawl's 11-15 s and 0.6-7.5 KB.
  Lightpanda is the closest MCP option (9-12 s, 169 B to 1 KB). For reading
  one public page, the `WEB_TOOLS` block's current "prefer Firecrawl for
  scraping" wording is too broad.
- JS-rendered page (T4): the built-in arm can't do it, and it spent 6 calls,
  51 s and 333k cached tokens finding that out. All three MCP arms answered
  in 10-16 s with one or two calls. This is the case the block was written
  for, and the MCP servers handle it.
- Search (T1): no clear winner. WebSearch used 2.0 KB and 13 s,
  `firecrawl_search` 2.7 KB and 19 s, and both were right. Nothing here
  argues for routing plain search away from the built-in.
- Crawl: not measured (see T6 above).
- browser-use is the cheapest in tokens (3-748 bytes in, output tokens level
  with the others), and 10-18 s per session holds up despite Chromium
  startup. It's the tool for interaction and logged-in sessions, which this
  bench didn't exercise. For a plain fetch, Lightpanda gets the same answer
  with less machinery.

Verdict: use the built-in tools first for a single static page or a plain
search. The MCP servers are worth it once the page needs JavaScript. Among
them, Lightpanda is the default because it's cheapest to run; switch to
browser-use when the task needs real interaction, or Firecrawl when you need
the full page as markdown or a multi-page crawl. The `WEB_TOOLS` block should
list them in that order, which is the reverse of what it says now.

## Follow-ups not covered here

- A crawl task on a site the model has never seen, so "follow Next" is
  actually followed.
- A search task with an unambiguous, obscure answer to replace T2.

## Verbatim follow-up (`verbatim.py`, 2026-09-16)

The risk left open above: WebFetch returns a summary, so does it paraphrase
when the task is "quote this exactly"? Four verbatim tasks, each matched
case-sensitively against strings read off the live pages with curl:

| ID | Task | Must contain |
|---|---|---|
| V1 | Full text of the first quote on quotes.toscrape.com/page/3 (319 chars) | `...so intimate that your hand upon my chest is my hand, so intimate that when I fall asleep your eyes close` |
| V2 | The `cargo install` command in the README at github.com/ngmeyer/librarian-mcp | `cargo install --git https://github.com/ngmeyer/librarian-mcp` |
| V3 | First `await tx.update(...)` line on orm.drizzle.team/docs/transactions | ``update(accounts).set({ balance: sql`${accounts.balance} - 100.00` }).where(eq(users.name, 'Dan'))`` |
| V4 | Default + four possible values of `python-preference` on docs.astral.sh/uv/reference/settings/ (a 420 KB page) | `"only-managed"`, `"managed"`, `"system"`, `"only-system"` |

Correctness: 12/12. Every arm reproduced every string exactly, including the
Neruda quote, the template literal with `${...}` and backticks, and the
quoted TOML values. WebFetch never paraphrased. Its "summary" is generated
from the prompt Claude passes it, so when the prompt says "quote this
verbatim", that's what comes back.

### Tool output per session, bytes

| Task | Built-in WebFetch | Firecrawl | Lightpanda |
|---|---|---|---|
| V1 | **319** | 4,360 | 521 |
| V2 | **363** | 23,688 | 23,763 |
| V3 | **223** | 7,197 | 13,155 |
| V4 | **546** | 68,527 | 3,744 |

### MCP / WebFetch calls per session

| Task | Built-in WebFetch | Firecrawl | Lightpanda |
|---|---|---|---|
| V1 | **1** | **1** | **1** |
| V2 | 2 | **1** | **1** |
| V3 | **1** | **1** | 3 |
| V4 | **1** | 22 | 4 |

### Session wall-clock, s

| Task | Built-in WebFetch | Firecrawl | Lightpanda |
|---|---|---|---|
| V1 | **14.3** | 15.1 | 16.4 |
| V2 | 22.3 | 19.8 | **11.7** |
| V3 | **13.5** | 16.5 | 15.1 |
| V4 | **14.2** | 228.0 | 23.0 |

### Cached input tokens per session

| Task | Built-in WebFetch | Firecrawl | Lightpanda |
|---|---|---|---|
| V1 | **102k** | 105k | 105k |
| V2 | 146k | 105k | **104k** |
| V3 | **102k** | 105k | 204k |
| V4 | **102k** | 2,144k | 338k |

### Reading it

- WebFetch's summary stays exact when the ask is precise: 4/4 verbatim at
  223-546 bytes and 13-22 s. So the block's "built-ins first for a single
  page" holds for exact-content lookups too. The case still untested is a
  vague ask ("what does this page say about X"), where the summariser
  decides what matters.
- The 420 KB page (V4) is where the whole-page tools broke. Firecrawl scraped
  it, hit what looks like a truncated payload (4 tool errors), and thrashed:
  22 MCP calls across scrape/search/map/developer_search/
  research_search_github, 228 s, 12,760 output tokens and 2.1M cached
  tokens, about 20x any other session in either bench. Lightpanda's
  `markdown` couldn't take the page whole either; it recovered through
  `tree` + `evaluate` in 4 calls, 23 s and 338k. WebFetch needed one call,
  546 bytes and 14 s. On a long reference page, the summariser is the tool
  to reach for.
- Firecrawl and Lightpanda returned the same bytes on V2 (23.7 KB, the whole
  GitHub README page). For exact content they cost the full page every time,
  while WebFetch costs only the answer.

Verdict with this added: the removal stands, on a stronger case than the
council had. The untested risk (WebFetch being lossy) didn't show up, and
the one scenario where Firecrawl was expected to shine, a big page, is where
it did worst.
