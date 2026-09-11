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

## Repo: private

The repo stores MCP server topology and setup scripts referencing personal
services (self-hosted Firecrawl, Obsidian vault, Bifrost instance). Kept
private by default; secrets themselves are never committed (see
`mcp/mcp-servers.json` placeholders) so it could be made public later after
a final scan.
