# bench

The measurements behind some of the decisions in `AGENTS.md`. Each subfolder
has its own harness and a `results.md` from the run it was built for.
`harness.py` is the shared `claude -p` session runner, using the same approach
as `tests/test_mcp_servers.py`.

None of this runs under `uv run pytest`. Each bench drives real `claude -p`
sessions, takes minutes and costs tokens. Run them as modules from the repo
root:

    uv run python -m bench.docs_retrieval.threearm
    uv run python -m bench.web_tools.webtools
    uv run python bench/vault_plugin/trial.py   # needs the scratch copies in its docstring

- `docs_retrieval/`: the vault mirror, Context7 and live Firecrawl, each asked
  the same 8 Drizzle questions. Result: use Context7 first. The mirror only
  pays off for docs Context7 doesn't cover.
- `web_tools/`: Firecrawl, Lightpanda and browser-use against the built-in
  WebSearch/WebFetch, on search, static fetch, JS-rendered fetch and a
  follow-the-links crawl. `verbatim.py` is a follow-up that checks WebFetch's
  summary against requests for exact text. Result: built-ins first,
  Lightpanda for JS pages. Firecrawl was taken out of the setup because of
  this bench.
- `vault_plugin/`: the claude-obsidian plugin, tried on a copy of the vault as
  a replacement for librarian-mcp. The trial covered adopt, index, retrieval
  quality, `wiki-query`/`save` sessions and a copy on `/mnt/c`. Result: not
  now. Its writes fail on drvfs, it only indexes `wiki/`, and each operation
  takes 5-30x as many turns as librarian-mcp.

`docs_retrieval` and `web_tools` both have a Firecrawl arm. `setup` no longer
installs Firecrawl, so to re-run those arms you need your own instance at
`FIRECRAWL_API_URL`: the self-hosted stack the results were measured
against, or Firecrawl Cloud with an API key. The other arms run against what
`setup` installs.
