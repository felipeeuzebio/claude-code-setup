# bench

One-off measurements behind decisions recorded in `AGENTS.md`. Each
subfolder is a self-contained harness plus a `results.md` write-up of the
run it was built for; `harness.py` is the shared `claude -p` session runner
(same technique as `tests/test_mcp_servers.py`). Nothing here is part of
`uv run pytest` - these drive real `claude -p` sessions, take minutes, and
cost tokens. Run them from the repo root as modules:

    uv run python -m bench.docs_retrieval.threearm
    uv run python -m bench.web_tools.webtools
    uv run python bench/vault_plugin/trial.py   # needs the scratch copies in its docstring

- `docs_retrieval/` - vault mirror vs Context7 vs Firecrawl live, 8 Drizzle
  questions x 3 arms. Verdict: Context7 first; the mirror only pays for docs
  Context7 doesn't cover.
- `web_tools/` - the web/browser MCP servers (Firecrawl, Lightpanda,
  browser-use) vs built-in WebSearch/WebFetch on search, static fetch,
  JS-rendered fetch and a follow-the-links crawl; `verbatim.py` is the
  follow-up checking WebFetch's summary against exact-text asks. Verdict:
  built-ins first; Lightpanda for JS pages; Firecrawl was removed from the
  setup on this evidence.
- `vault_plugin/` - the claude-obsidian Claude Code plugin tried as a
  replacement for librarian-mcp, on a copy of the vault: adopt, index,
  retrieval quality, `wiki-query`/`save` sessions, and a copy on `/mnt/c`.
  Verdict: not now - its writes fail on drvfs, it only indexes `wiki/`, and
  each operation costs 5-30x librarian-mcp in turns.

Both benches have a Firecrawl arm. `setup` no longer installs Firecrawl, so
re-running those arms needs an instance of your own at `FIRECRAWL_API_URL`
(the self-hosted stack the results were measured against, or Firecrawl
Cloud with an API key). The other arms run against what `setup` installs.
