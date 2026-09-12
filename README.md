# claude-code-setup

Personal Claude Code environment configuration: an MCP gateway (Bifrost), a curated
set of MCP servers, and a reusable language-agnostic `CLAUDE.md` starter.

## Layout

```
setup.sh              One-shot setup for Linux (native or WSL2) and macOS
setup.ps1             One-shot setup for native Windows (Lightpanda needs WSL2 though)
.env.example          Secrets/flags setup.sh and setup.ps1 read, plus self-hosted Firecrawl's own env
AGENTS.md              Why things are configured the way they are - read before changing MCP server choices or script behavior
CLAUDE_TEMPLATE.md     The CLAUDE.md-generation prompt (starter structure embedded) setup.sh/setup.ps1 offer to run
mcp/                   Standalone MCP server definitions (works with or without Bifrost)
scripts/               Installer/merge helpers used by setup.sh/setup.ps1, incl. self-hosted Firecrawl bring-up
githooks/              commit-msg hook enforcing Conventional Commits (wired up by setup.sh/setup.ps1)
```

## MCP servers included

| Server | Role | Notes |
|---|---|---|
| GitHub | repo/issue/PR operations | needs `GITHUB_PERSONAL_ACCESS_TOKEN` |
| Context7 | live library docs lookup | no key required |
| Firecrawl | web scraping/crawling | self-hosted via Docker Compose, see `scripts/setup-firecrawl.sh` |
| Obsidian (librarian-mcp) | read/search/write your vault + graph analytics | reads the vault off disk, no Obsidian process needed |
| browser-use | low-level browser control, Claude drives the steps | self-hosted via `uvx`, no API key needed |
| Lightpanda | fast local browser engine, text/DOM-oriented tools | its own native MCP server (`lightpanda mcp`, stdio), no CDP wrapper |
| Codegraph | codebase knowledge graph (callers/callees/impact) | already installed locally, registered directly |

Graphify was evaluated and intentionally left out — see `AGENTS.md`.

## Quickstart

```bash
cp .env.example .env   # fill in what you have; unset vars just get skipped
./setup.sh             # Linux (native or WSL2) / macOS
# or, on native Windows:
./setup.ps1
```

Installs Codegraph, librarian-mcp, and (Linux/macOS only) Lightpanda;
registers whichever MCP servers have their required secret/path set into
`~/.claude.json` (backing it up first); brings up self-hosted Firecrawl if
Docker is available; and starts Bifrost. Idempotent - re-run anytime, e.g.
after adding a secret to `.env`. Output uses
[gum](https://github.com/charmbracelet/gum) if it's on your PATH, with a
plain-text fallback otherwise - no dependency required either way. Ctrl+C
at any point quits cleanly.

It prints what's left for you to do by hand: generate a Bifrost virtual
key and register any servers you'd rather gateway through it, both via the
web UI at http://localhost:8080 (see https://docs.getbifrost.ai).

If this repo has no `CLAUDE.md` yet, you're also asked whether to generate
one now from `CLAUDE_TEMPLATE.md`, filled in from the repo's actual
manifests/scripts/layout rather than a generic template. Say no (or run
non-interactively) to just get the prompt printed for pasting into any
Claude Code session, here or elsewhere. An existing `CLAUDE.md` is never
overwritten.

## Credit

The CLAUDE.md template embedded in `CLAUDE_TEMPLATE.md` is adapted from
[abhishekray07/claude-md-templates](https://github.com/abhishekray07/claude-md-templates)
and cross-checked against
[centminmod/my-claude-code-setup](https://github.com/centminmod/my-claude-code-setup).

The Obsidian MCP choice (`librarian-mcp`) came from
[hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) -
the largest curated list of Claude Code resources (skills, hooks,
statuslines, MCP servers, agent orchestration).
