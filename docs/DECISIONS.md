# Setup decisions

Recorded 2026-09-11, so future-me remembers *why*, not just *what*.

## Bifrost as the MCP gateway

Bifrost (Maxim AI) was chosen over running each MCP server directly against
Claude Code because it doubles as an LLM gateway (cost/observability across
model calls) and an MCP aggregator (one `/mcp` endpoint fronting every
downstream tool server), in a single self-hostable Go binary. No other
open-source option combines both roles.

Caveat: Bifrost's own docs don't fully spell out the config-file schema for
registering downstream MCP servers — that's done through its web UI
(`http://localhost:8080`) or management API, not by hand-editing JSON we
control. Treat `bifrost/SETUP.md` as the source of truth and re-check
`docs.getbifrost.ai` if the UI has moved things around.

## Firecrawl: self-hosted via Docker, not cloud

Chose to enable Docker Desktop's WSL integration (rather than installing
Docker Engine natively in the WSL2 distro, or just using Firecrawl Cloud)
because Docker Desktop was already the assumed setup. `docker --version`
was not found in-distro at the start of this session but was present by
the time `scripts/setup-firecrawl.sh` ran — confirming WSL integration was
enabled correctly.

Two real issues came up bringing the stack up for the first time, both
fixed and captured in `scripts/setup-firecrawl.sh` / `firecrawl/.env.example`:

- **RabbitMQ `EACCES` on `.erlang.cookie`** on the very first `up` - a
  known Docker-Desktop-on-WSL2 anonymous-volume permission quirk. Fixed by
  `docker compose down -v && docker compose up -d` once; if it recurs,
  it's the same class of issue, not a config problem.
- **`NUQ_BACKEND=postgres` is not a valid value** - the API only accepts
  `pg` or `fdb`. Set to `pg` since this compose file brings up
  `nuq-postgres`.

Verified working end-to-end with a live `POST /v1/scrape` against
`https://example.com` through the running container, not just a port
check.

## browser-use + Lightpanda: both, not either/or

These aren't competing choices — they sit at different layers:

- **browser-use** is an agent framework: give it a task in natural language,
  it decides the steps. Kept as the hosted MCP (`api.browser-use.com/mcp`)
  for exploratory, task-level browsing.
- **Lightpanda** is a browser *engine* (CDP-compatible, built from scratch in
  Zig, ~11x faster / ~1/16th the memory of headless Chrome). It's wired in as
  the backend for the Playwright MCP via `--cdp-endpoint`, for
  performance-sensitive scripted scraping where you already know the steps.

Use browser-use when you'd otherwise write scraping logic by hand; use the
Lightpanda-backed Playwright MCP when you already have a deterministic
sequence and just want it fast and cheap to run repeatedly.

## Codegraph over Graphify

Both are codebase-knowledge-graph MCP servers with heavy feature overlap
(symbol graphs, impact analysis, token-budgeted context). Codegraph was
kept because:

- It was already installed locally (`codegraph` CLI, v1.5.0) — zero extra
  install cost.
- It has a broader tool surface (9 MCP tools: search, context, callers/
  callees, impact, explore, node, files, status) versus Graphify's
  graph-analysis-only focus.
- Running both would mean two overlapping graph indexes to keep in sync
  for no added capability — pure maintenance cost.

Ripgrep alone was ruled out as *sufficient* (not as a tool to drop) because
it can't answer structural questions — "who calls this", "what breaks if I
change this" — that Codegraph answers directly from a persisted graph
instead of re-deriving them from text search every time.

## Obsidian: librarian-mcp instead of mcp-obsidian

Swapped after checking [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)
(53.9k stars, the largest curated Claude Code resource list) which surfaced
several Obsidian options under its "Obsidian" section. Went with
[librarian-mcp](https://github.com/ngmeyer/librarian-mcp) over the
originally-planned `MarkusPfundstein/mcp-obsidian` because:

- It reads the vault directory straight off disk - Obsidian doesn't need
  to be running, and there's no dependency on the community "Local REST
  API" plugin or an `OBSIDIAN_API_KEY`.
- It sidesteps `mcp-obsidian`'s known stability issue (pinned to Python
  MCP SDK `<2.0.0`, `BrokenPipeError` on newer SDKs).
- Broader tool surface: 17 tools including trigram search, auto-wikilinks
  on write, and real graph analytics (Louvain communities, PageRank,
  shortest-path) versus mcp-obsidian's basic read/search/write.
- Ships a Linux x86_64 release binary + installer script, so it works
  fine on this WSL2 box without a Homebrew dependency.

Also worth a look but not adopted here: `agentcairn`, `claude-bedrock`,
and `claude-obsidian` from the same list - all take a more opinionated
"second brain" / Zettelkasten angle rather than a plain MCP server, which
is more setup than this pass needed.

## setup.sh/setup.ps1: skip rather than write broken entries

Both scripts (and the `scripts/merge-mcp-config.js` they share) only add
an MCP server to `~/.claude.json` once its required secret/path is
present - a `github` entry with a placeholder token would fail on first
use, and a silently-broken MCP server is worse than one that's just not
there yet. Missing pieces are listed at the end of the run instead, so
re-running after adding one line to `.env` is the whole fix.

Lightpanda is Linux/macOS-only (no native Windows build as of this
writing), so `setup.ps1` skips it outright rather than half-installing;
the full stack including Lightpanda needs `setup.sh` under WSL2 on
Windows machines.

## Repo: private

The repo stores MCP server topology and setup scripts referencing personal
services (self-hosted Firecrawl, Obsidian vault, Bifrost instance). Kept
private by default; secrets themselves are never committed (see
`mcp/mcp-servers.json` placeholders) so it could be made public later after
a final scan.
