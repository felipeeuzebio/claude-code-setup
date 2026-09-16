# Web tools: Firecrawl / Lightpanda / browser-use vs built-in WebSearch & WebFetch

Date: 2026-09-16. The global `WEB_TOOLS` block (written by `setup` into
`~/.claude/CLAUDE.md`) tells Claude to prefer the registered MCP servers over
the built-in WebSearch/WebFetch. This measures whether that's right, on the
task kinds the block routes between them. Harness: `webtools.py`, same
`claude -p` technique as `docs_retrieval/` (model: sonnet, one arm's tools
per session, everything else denied).

## Arms

| Arm | Tools allowed | Runs the search tasks? |
|---|---|---|
| Built-in WebSearch/WebFetch | `WebSearch`, `WebFetch` - no MCP servers at all | yes |
| Firecrawl | `firecrawl_search`, `firecrawl_scrape`, `firecrawl_map`, `firecrawl_crawl` (self-hosted at `FIRECRAWL_API_URL`) | yes |
| Lightpanda | `markdown`, `goto`, `tree`, `extract`, `evaluate`, `links`, ... (native `lightpanda mcp`) | no - no search tool |
| browser-use | `browser_exec` against a headless Chromium on port 9223 | no - no search tool |

## Tasks

| ID | Kind | Task | Expected answer |
|---|---|---|---|
| T1 | search | URL of the official Model Context Protocol specification | `modelcontextprotocol.io` |
| T2 | search | GitHub owner/name of the librarian-mcp Obsidian MCP server | `ngmeyer/librarian-mcp` |
| T3 | static fetch | The h1 of https://example.com | `Example Domain` |
| T4 | JS-rendered fetch | Number of quotes on https://quotes.toscrape.com/js/ (list is built client-side) | `COUNT=10` |
| T5 | static fetch | Author of the first quote on https://quotes.toscrape.com/page/2/ | `Marilyn Monroe` |
| T6 | crawl | Follow "Next" from https://quotes.toscrape.com/ to the last page | `/page/10/` |

A session counts as correct only if the regex matches **and** the arm's own
tool was called at least once - an answer from memory scores 0. Every session
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

- **T4, built-in: a false regex pass.** The answer contains `COUNT=10`, but
  the model said in the same breath that "WebFetch can't execute JavaScript,
  so it can't directly confirm the JS-rendered count" and inferred 10 from
  the non-JS page - after 6 WebFetch/WebSearch calls and 51 s. On the thing
  T4 measures (can this arm see a JS-rendered page?) that is a failure, and
  the table scores it as one.
- **T2 is inconclusive.** Two unrelated projects are named `librarian-mcp`.
  The built-in arm found both and asked which one was meant; Firecrawl
  returned the other one. The task was underspecified, so T2 is excluded
  from the totals.

And one design flaw: **T6 did not measure crawling.** quotes.toscrape.com is
a well-known scraping sandbox and every arm jumped straight to `/page/10/`
and verified it had no Next link - one call for Firecrawl and Lightpanda,
three WebFetch calls for built-in (pages 1, 10 and 11). A real multi-page
test needs a site the model has never seen.

## Tool output per session, bytes

Bytes every tool result put into the session - the tokens-into-context
proxy (~4 bytes per token). Bold = cheapest arm on that task.

| Task | Built-in WebSearch/WebFetch | Firecrawl | Lightpanda | browser-use |
|---|---|---|---|---|
| T1 | **2,032** | 2,787 | — | — |
| T2 | 4,688 | **2,323** | — | — |
| T3 | 53 | 624 | 169 | **15** |
| T4 | 6,684 | 2,059 | 3,322 | **3** |
| T5 | 184 | 7,510 | 1,041 | **15** |
| T6 | **340** | 2,780 | 3,755 | 748 |
| **Median** | **1,186** | **2,552** | **2,182** | **15** |

Why the built-in and browser-use numbers are so small: `WebFetch` does not
return the page, it returns a side-model **summary** of it (53 bytes for
example.com), and `browser_exec` returns only what the generated Python
`print`s. Firecrawl and Lightpanda return the page itself as markdown.
For WebFetch, cheap is also lossy - fine for a heading or a name, untested
here for verbatim code or config values.

Bytes-in is only part of the bill, so the session's own `usage` (from the
`result` event) is below. Output tokens are what Claude wrote - including
the Python every `browser_exec` call carries in its *input*, which the bytes
table can't see. Cached input tokens are the system prompt + tool schemas +
global CLAUDE.md re-read on every turn (~100k per turn here).

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

Two things fall out. browser-use's Python is short: its output tokens sit
with Lightpanda's and Firecrawl's, so the 3–15 B results are cheap for real,
not an artifact. And **turn count dominates total tokens**: built-in T4's six
calls re-read 333k cached tokens against ~104k for any one-call arm. A few
KB more or less of tool output is noise next to one extra turn.

## Session wall-clock, s

Whole `claude -p` session including startup. Bold = fastest arm on that
task. browser-use ran one session at a time (it shares the one Chromium);
the other arms ran three in parallel, which may inflate theirs slightly.

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

- **Static page (T3, T5): built-in WebFetch wins on both axes.** 8.5–9 s and
  under 200 bytes against Firecrawl's 11–15 s and 0.6–7.5 KB. Lightpanda is
  the closest MCP option (9–12 s, 169 B–1 KB). For "read this one public page",
  the `WEB_TOOLS` block's current "prefer Firecrawl for scraping" wording is
  over-broad.
- **JS-rendered page (T4): the built-in arm cannot do it**, and spent 6 calls,
  51 s and 333k cached tokens finding that out. All three MCP arms answered in 10–16 s with one
  or two calls. This is the case the block exists for, confirmed.
- **Search (T1): a wash.** WebSearch 2.0 KB / 13 s vs `firecrawl_search`
  2.7 KB / 19 s, both correct. No reason to route plain search away from the
  built-in on this evidence.
- **Crawl: unmeasured** (see T6 above).
- **browser-use** is genuinely cheapest in tokens (3–748 bytes in, output
  tokens level with the others), and 10–18 s per session is competitive
  despite Chromium startup. It's the right tool for
  interaction and logged-in sessions, which this bench did not exercise; for
  a plain fetch Lightpanda gets the same answer with less machinery.

**Verdict:** the built-in tools are the right *first* choice for a single
static page or a plain search; the MCP servers earn their place the moment
the page needs JavaScript, and there the choice between them is Lightpanda
(cheapest to run) unless real interaction is needed (browser-use) or the
result must be the full page as markdown / a multi-page crawl (Firecrawl).
The `WEB_TOOLS` block should say that order, not the reverse.

## Follow-ups not covered here

- A crawl task on a site the model has never seen, so "follow Next" is
  actually followed.
- A search task with an unambiguous, obscure answer to replace T2.

## Verbatim follow-up (`verbatim.py`, 2026-09-16)

The open risk above: WebFetch returns a *summary*, so does it paraphrase when
the task is "quote this exactly"? Four tasks, each verbatim, matched
case-sensitively against strings read off the live pages with curl:

| ID | Task | Must contain |
|---|---|---|
| V1 | Full text of the first quote on quotes.toscrape.com/page/3 (319 chars) | `...so intimate that your hand upon my chest is my hand, so intimate that when I fall asleep your eyes close` |
| V2 | The `cargo install` command in the README at github.com/ngmeyer/librarian-mcp | `cargo install --git https://github.com/ngmeyer/librarian-mcp` |
| V3 | First `await tx.update(...)` line on orm.drizzle.team/docs/transactions | ``update(accounts).set({ balance: sql`${accounts.balance} - 100.00` }).where(eq(users.name, 'Dan'))`` |
| V4 | Default + four possible values of `python-preference` on docs.astral.sh/uv/reference/settings/ (a 420 KB page) | `"only-managed"`, `"managed"`, `"system"`, `"only-system"` |

**Correctness: 12/12.** Every arm reproduced every string exactly - the
Neruda quote, the template literal with `${...}` and backticks, the quoted
TOML values. WebFetch did not paraphrase once. Its "summary" is generated
from the prompt Claude passes it, so when the prompt says "quote this
verbatim" that is what comes back.

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

- **WebFetch's summary is not lossy when the ask is precise.** 4/4 verbatim
  at 223-546 bytes and 13-22 s. The block's "built-ins first for a single
  page" holds for exact-content lookups too. The remaining caveat is the
  case not tested: a vague ask ("what does this page say about X") where
  the summariser decides what matters.
- **The 420 KB page (V4) is where the whole-page tools broke.** Firecrawl
  scraped it, hit what looks like a truncated payload (4 tool errors), and
  thrashed: 22 MCP calls across scrape/search/map/developer_search/
  research_search_github, 228 s, 12,760 output tokens, 2.1M cached tokens -
  ~20x any other session in either bench. Lightpanda's `markdown` also
  couldn't take the page whole; it recovered via `tree` + `evaluate` in 4
  calls / 23 s / 338k. WebFetch: one call, 546 bytes, 14 s. On a long
  reference page the summariser is the right tool, not the workaround.
- Firecrawl and Lightpanda returned identical bytes on V2 (23.7 KB - the
  whole GitHub README page): for exact content they cost the full page
  every time, WebFetch costs the answer.

**Verdict, with this added:** the removal stands, and the case is stronger
than the council had - the untested risk (WebFetch lossiness) did not
materialise, and the one scenario where Firecrawl was expected to shine
(a big page) is where it did worst.
