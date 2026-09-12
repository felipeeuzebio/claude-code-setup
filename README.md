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

This installs Codegraph, librarian-mcp, and (Linux/macOS only) Lightpanda,
registers whichever MCP servers have their required secret/path set into
`~/.claude.json` (backing it up first), brings up self-hosted Firecrawl if
Docker is available, and starts Bifrost. It's idempotent - re-run anytime,
e.g. after adding a secret to `.env`.

Output is styled with [gum](https://github.com/charmbracelet/gum) if it's
on your PATH; if not, the script downloads a copy into a throwaway temp
directory for just this run and deletes it on exit - nothing gets
installed system-wide, and everything still works in plain text if gum
can't be reached at all (offline, unsupported OS/arch). Styling is kept
minimal on purpose (a single foreground color per line, no borders/boxes),
and install spinners use gum's plain ASCII spinner rather than its default
Unicode one, which can render as mangled characters on fonts without full
Braille Pattern support. Ctrl+C at any point - including at the CLAUDE.md
prompt or during an install spinner - quits the whole thing cleanly rather
than just skipping that one step.

It prints exactly what's left afterward: generating a Bifrost virtual key
(an interactive UI step) and adding any servers you'd rather gateway
through Bifrost instead of running direct via its web UI at
http://localhost:8080 (Settings → MCP → Add Server) - see
https://docs.getbifrost.ai for the full config schema.

Separately, if this repo has no `CLAUDE.md` yet, `setup.sh`/`setup.ps1` ask
whether to generate one now via `claude -p` using `CLAUDE_TEMPLATE.md`
(which fills in its embedded starter structure from the repo's
actual manifests/scripts/layout - not Claude Code's generic `/init` output).
Say no (or run non-interactively) and it just prints that same prompt so you
can paste it into any Claude Code session, here or in another project,
whenever you're ready. It never overwrites an existing `CLAUDE.md`.

## Credit

The CLAUDE.md template embedded in `CLAUDE_TEMPLATE.md` is adapted from
[abhishekray07/claude-md-templates](https://github.com/abhishekray07/claude-md-templates)
and cross-checked against
[centminmod/my-claude-code-setup](https://github.com/centminmod/my-claude-code-setup).

The Obsidian MCP choice (`librarian-mcp`) and general future discovery came
from [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) -
the largest curated list of Claude Code resources (skills, hooks,
statuslines, MCP servers, agent orchestration). Worth a periodic re-check
as this setup evolves.
