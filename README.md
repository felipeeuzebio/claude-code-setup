# claude-code-setup

Personal Claude Code environment configuration: an MCP gateway (Bifrost), a curated
set of MCP servers, and a reusable language-agnostic `CLAUDE.md` starter.

## Layout

```
setup.sh          One-shot setup for Linux/macOS/WSL2
setup.ps1         One-shot setup for native Windows (Lightpanda needs WSL2 though)
.env.example      Optional secrets/flags setup.sh and setup.ps1 read
bifrost/          Bifrost MCP gateway install + config notes
mcp/              Standalone MCP server definitions (works with or without Bifrost)
firecrawl/        Self-hosted Firecrawl (Docker Compose) setup
claude-md/        Reusable, language-agnostic CLAUDE.md starter template
scripts/          Installer/merge helpers used by setup.sh/setup.ps1
docs/DECISIONS.md Why things are configured the way they are
```

## MCP servers included

| Server | Role | Notes |
|---|---|---|
| GitHub | repo/issue/PR operations | needs `GITHUB_PERSONAL_ACCESS_TOKEN` |
| Context7 | live library docs lookup | no key required |
| Firecrawl | web scraping/crawling | self-hosted via Docker Compose, see `firecrawl/` |
| Obsidian (librarian-mcp) | read/search/write your vault + graph analytics | reads the vault off disk, no Obsidian process needed |
| browser-use | agentic browsing (task → actions) | hosted API, needs `BROWSER_USE_API_KEY` |
| Lightpanda | fast local CDP browser engine | pairs with the Playwright MCP via `--cdp-endpoint` |
| Codegraph | codebase knowledge graph (callers/callees/impact) | already installed locally, registered directly |

Graphify was evaluated and intentionally left out — see `docs/DECISIONS.md`.

## Quickstart

```bash
cp .env.example .env   # fill in what you have; unset vars just get skipped
./setup.sh             # Linux/macOS/WSL2
# or, on native Windows:
./setup.ps1
```

This installs Codegraph, librarian-mcp, and (Linux/macOS only) Lightpanda,
registers whichever MCP servers have their required secret/path set into
`~/.claude.json` (backing it up first), brings up self-hosted Firecrawl if
Docker is available, and starts Bifrost. It's idempotent - re-run anytime,
e.g. after adding a secret to `.env`.

It prints exactly what's left afterward: generating a Bifrost virtual key
(an interactive UI step) and adding any servers you'd rather gateway
through Bifrost instead of running direct. See `bifrost/SETUP.md` for that
part in detail.

Separately, copy `claude-md/GENERIC_TEMPLATE.md` into any project as
`CLAUDE.md` and fill in the blanks.

## Credit

`claude-md/GENERIC_TEMPLATE.md` is adapted from
[abhishekray07/claude-md-templates](https://github.com/abhishekray07/claude-md-templates)
and cross-checked against
[centminmod/my-claude-code-setup](https://github.com/centminmod/my-claude-code-setup).

The Obsidian MCP choice (`librarian-mcp`) and general future discovery came
from [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) -
the largest curated list of Claude Code resources (skills, hooks,
statuslines, MCP servers, agent orchestration). Worth a periodic re-check
as this setup evolves.
