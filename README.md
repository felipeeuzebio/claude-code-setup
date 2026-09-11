# claude-code-setup

Personal Claude Code environment configuration: an MCP gateway (Bifrost), a curated
set of MCP servers, and a reusable language-agnostic `CLAUDE.md` starter.

## Layout

```
bifrost/          Bifrost MCP gateway install + config notes
mcp/              Standalone MCP server definitions (works with or without Bifrost)
firecrawl/        Self-hosted Firecrawl (Docker Compose) setup
claude-md/        Reusable, language-agnostic CLAUDE.md starter template
scripts/          Helper scripts (env verification, Firecrawl bring-up)
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

1. Read `bifrost/SETUP.md` and bring up the gateway.
2. Fill in real secrets in `mcp/mcp-servers.json` (copy the relevant server blocks
   into `~/.claude.json` or register them through the Bifrost UI).
3. If you want self-hosted Firecrawl, run `scripts/setup-firecrawl.sh`.
4. Copy `claude-md/GENERIC_TEMPLATE.md` into any project as `CLAUDE.md` and fill
   in the blanks.

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
