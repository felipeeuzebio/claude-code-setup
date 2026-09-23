# Docs retrieval: vault mirror vs Context7 vs Firecrawl live

Date: 2026-09-15. This answers the plan's Stage-0 question: does mirroring a
doc site into the Obsidian vault (`Indexed Docs/<docname>/<version>/`) beat
just asking Context7 or Firecrawl? The corpus is
`Indexed Docs/drizzle/1.0-beta/`, 187 pages with the per-dialect subtrees and
changelog excluded, built with:

```
uv run docs-index drizzle 1.0-beta https://orm.drizzle.team/docs \
  --limit 5000 --workers 6 \
  --exclude '/docs/(sqlite|mysql|cockroach|mssql|singlestore)/' \
  --exclude '/docs/latest-releases/'
```

(771 pages were mapped, 546 of them per-dialect near-duplicates of the pg
pages. `latest-releases.md` slipped past the exclude because the regex wanted
a trailing slash, and was deleted by hand.)

## One-time costs

| | |
|---|---|
| Crawl wall-clock | 8m10s (188 pages, 6 workers, 0 failures) |
| Context tokens | 0 (script hits Firecrawl HTTP directly) |
| Boilerplate removed | 20% (2.03M -> 1.64M chars) |
| Disk | ~1.6 MB |

## Questions (natural-language, not keyword-tuned)

| ID | Question |
|---|---|
| Q1 | How do I select only specific columns instead of all of them? |
| Q2 | How do I do a LEFT JOIN and what does the result shape look like? |
| Q3 | How do I fetch a user with all their posts in one query (relational API)? |
| Q4 | How do I run multiple writes in a transaction and roll back? |
| Q5 | How do I generate SQL migration files from my schema with drizzle-kit? |
| Q6 | How do I add a unique index on a column? |
| Q7 | How do I do an upsert (insert or update on conflict)? |
| Q8 | How do I define a Postgres table with a serial PK and a timestamp column? |

## Arm C: vault (`library_search` -> `library_read`), measured in-session

| Question | Top-3 `library_search` results (expected page in bold) | Page read | Page size (KB / ~tokens) | Answer on the page? |
|---|---|---|---|---|
| Q1 | sql, joins, **select** (rank 3) | select.md | 24.4 KB / ~6.1k tok | yes |
| Q2 | **joins**, aliases, guides-count-rows | joins.md | 11.8 KB / ~3.0k tok | yes |
| Q3 | **rqb**, guides-include-or-exclude-columns, relations | rqb.md | 24.6 KB / ~6.2k tok | yes |
| Q4 | **transactions**, connect-nile, connect-neon | transactions.md | 3.5 KB / ~0.9k tok | yes |
| Q5 | **drizzle-kit-generate**, migrations, drizzle-kit-migrate | drizzle-kit-generate.md | 11.8 KB / ~2.9k tok | yes |
| Q6 | **indexes-constraints**, guides-unique-case-insensitive-email, generated-columns | indexes-constraints.md | 11.8 KB / ~2.9k tok | yes |
| Q7 | **guides-upsert**, insert, v0-v1-changes | guides-upsert.md | 12.8 KB / ~3.2k tok | yes |
| Q8 | indexes-constraints, guides-timestamp-default-value, column-types | column-types.md | 31.3 KB / ~7.8k tok | yes, but sql-schema-declaration.md (13 KB) is the better page and was not in top 3 |

- Correctness: 8/8 pages contain the answer. Rank-1 hit: 6/8.
- Round trips: 2 per question (search + read). No question needed a second
  read.
- Tokens in: ~75 for the search plus 0.9k-7.8k for the read, median ~3.1k
  per question.
- Latency: local disk, so search <1s and read instant, with no network.

### librarian-mcp search behaviour (affects how arm C should be driven)

- Multi-word queries are scored as a bag of words with no phrase matching,
  and they return empty snippets. A sentence copied verbatim from `joins.md`
  didn't bring `joins.md` into the top 3, because `Drizzle`/`ORM` appear on
  every page.
- Single-word queries return snippets and low per-term scores.
- Without snippets, the agent ranks candidates by filename. Bare readable
  slugs (`select`, `joins`, `rqb`) make that easy, which is the payoff of the
  layout decision.
- A whole-page read is the unit of retrieval. `library_read` has no range or
  section option, so page size is the token cost. The 24-31 KB pages
  (select, rqb, column-types) are where arm C is weakest.
- Corpus hygiene matters more than you'd expect: removing one changelog page
  moved `rqb` from rank 2 to rank 1.

### Index lifecycle (operational)

- librarian-mcp indexes once at process start and has no refresh tool.
- Each Claude Code conversation spawns its own server. `/clear` and `/mcp`
  don't respawn it, but killing the process does: Claude Code respawns it
  lazily on the next tool call, with context intact.
- An external write to the vault is invisible to every open session until
  that session's server is recycled.

## Three arms, measured identically (`threearm.py`)

All three arms ran as fresh `claude -p` sessions (model: sonnet), each locked
to one MCP server via `--strict-mcp-config`, with WebFetch/WebSearch/Bash/Read
denied. Correctness is a fixed regex on the final answer (see `QUESTIONS`).
"Tool KB" is the bytes returned by all tool calls in the session, the proxy
for tokens into context. 24 sessions; raw records go to `results.jsonl`,
which is regenerated on each run and not committed.

| Arm | Correct answers | MCP calls per question (mean) | Tool output per question, KB (median) | Tool output, KB (min–max) | Session wall-clock, s (median) |
|---|---|---|---|---|---|
| A: Context7 | **8/8** | 2.1 | **5.6** | 4.1–8.9 | 19.9 |
| B: Firecrawl live | **8/8** | 1.4 | 26.4 | 11.0–47.4 | 27.6 |
| C: vault | **8/8** | 2.3 | 13.8 | 5.7–42.2 | **13.7** |

Per question below. Wall-clock is the whole `claude -p` session. Bold marks
the cheapest and the fastest arm on each question. All 24 answers were
correct.

| Question | Tool output, KB (Context7) | Tool output, KB (Firecrawl) | Tool output, KB (Vault) | Wall-clock, s (Context7) | Wall-clock, s (Firecrawl) | Wall-clock, s (Vault) | MCP calls (Context7) | MCP calls (Firecrawl) | MCP calls (Vault) |
|---|---|---|---|---|---|---|---|---|---|
| Q1 | **4.7** | 47.4 | 11.7 | 18.2 | 26.7 | **12.9** | 2 | 1 | 2 |
| Q2 | **5.8** | 15.6 | 13.7 | 26.9 | 19.8 | **14.4** | 2 | 1 | 3 |
| Q3 | **4.8** | 11.0 | 26.2 | 19.7 | 19.8 | **17.8** | 2 | 2 | 2 |
| Q4 | **5.5** | 34.1 | 5.7 | 20.1 | 31.0 | **11.9** | 2 | 1 | 2 |
| Q5 | **4.1** | 17.8 | 13.8 | **15.4** | 28.1 | 23.6 | 2 | 2 | 2 |
| Q6 | **6.5** | 37.6 | 13.8 | 19.3 | 27.1 | **14.4** | 2 | 1 | 2 |
| Q7 | **6.1** | 18.7 | 14.7 | 20.9 | 46.1 | **11.1** | 2 | 2 | 2 |
| Q8 | **8.9** | 38.6 | 42.2 | 26.2 | 34.2 | **12.5** | 3 | 1 | 3 |
| **Median** | **5.6** | **26.4** | **13.8** | **19.9** | **27.6** | **13.7** | 2 | 1 | 2 |

Every arm also pays one `ToolSearch` round trip to load its deferred MCP tool
schema. Its result isn't text, so it adds nothing to the KB column, and it
isn't an MCP call. Every arm pays it once, so it cancels out either way.

### Reading it against the plan's table

- Correctness is a three-way tie, so retrieval quality isn't the problem.
- C vs A: Context7 uses 2.5x fewer tokens (5.6 KB vs 13.8 KB). The plan said
  "C matches A on tokens → don't build", and C doesn't even match. For docs
  Context7 covers, the mirror isn't worth the risk of going stale.
- C vs B: the vault wins, 2x on tokens (13.8 vs 26.4 KB) and 2x on latency.
  This is the case below the Context7 line. `firecrawl_search` returns whole
  pages for several results at once (35-47 KB on Q1/Q4/Q6/Q8).
- Latency: C is fastest outright (13.7s vs 19.9s vs 27.6s, whole session).

Verdict: the plan's "expected result". Context7 first, always. The mirror is
only for docs Context7 doesn't cover, where it beats live Firecrawl by about
2x on both tokens and latency.

### Why Context7 uses fewer tokens

Context7 returns selected passages, and `library_read` returns whole pages.
The vault's unit of retrieval is the file, and `library_read` has no section
or range option, so the cost is however big the page is: 42 KB on Q8, which
took two reads (`column-types.md` 31 KB + `sql-schema-declaration.md`
13 KB). From the client side, the only fix is to split pages into smaller
files at crawl time, e.g. one per H2. That's a Stage-1 question, and only
worth asking for the non-Context7 niche.

### The routing gap (found while building the harness)

In a fresh session with no hint, the model never looked in the vault. It ran
ToolSearch for `context7`, `firecrawl`, `WebFetch`, `fetch url` and
`search web`, six tries in all, then gave up. The deferred `library_*` tool
names say nothing about documentation, and the global `WEB_TOOLS` block never
mentions the vault, so arm C fails before retrieval starts. The measurement
above gives every arm the same one-line hint naming its tools; without it,
arm C scores 0/8 on this design. If the mirror gets built for the
non-Context7 niche, the `WEB_TOOLS` block has to name the vault as a doc
source and say when to prefer it over Firecrawl. The plan deferred those
"routing lines", but the mirror doesn't work without them.

## Follow-up conditions not covered here

- Dialect-duplicate stress: re-crawl including the 5 dialect subtrees (546
  near-duplicate pages) and re-run the same 8 questions. The plan assigned
  this disambiguation test to shadcn/ui.
- A second Drizzle version alongside, to confirm path-only disambiguation.
