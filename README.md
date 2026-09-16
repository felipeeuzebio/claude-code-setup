# claude-code-setup

Personal Claude Code environment configuration: an MCP gateway (Bifrost), a curated
set of MCP servers, and a reusable language-agnostic `CLAUDE.md` starter.

## Layout

```
setup.sh              Thin wrapper: checks uv is present, execs `uv run setup`
setup.ps1             Same, for native Windows (Lightpanda needs WSL2 though)
src/setup/             The actual setup logic - a uv-managed Python package (see pyproject.toml)
tests/                 pytest suite: fast unit tests + the live MCP integration suite (`uv run pytest`)
.env.example          Secrets/flags setup.sh and setup.ps1 read
AGENTS.md              Why things are configured the way they are - read before changing MCP server choices or script behavior
CLAUDE_TEMPLATE.md     The CLAUDE.md-generation prompt (starter structure embedded) setup.sh/setup.ps1 offer to run
mcp-servers.json       Standalone MCP server definitions (works with or without Bifrost)
githooks/              commit-msg hook enforcing Conventional Commits (wired up by setup.sh/setup.ps1) - plain bash, unrelated to the Python package
bench/                 Measurements behind the tool choices (live `claude -p` benches + write-ups) - not part of pytest
```

## MCP servers included

| Server | Role | Notes |
|---|---|---|
| GitHub | repo/issue/PR operations | needs `GITHUB_PERSONAL_ACCESS_TOKEN` |
| Context7 | live library docs lookup | no key required |
| browser-use | low-level browser control, Claude drives the steps | self-hosted via `uvx`, no API key needed |
| Lightpanda | fast local browser engine, text/DOM-oriented tools | its own native MCP server (`lightpanda mcp`, stdio), no CDP wrapper |
| Codegraph | codebase knowledge graph (callers/callees/impact) | already installed locally, registered directly |

Obsidian is not part of this setup any more - the servers and plugins tried
are recorded in `AGENTS.md` for when it is picked up again.

Graphify was evaluated and intentionally left out, and self-hosted Firecrawl was removed after benchmarking against the built-in WebSearch/WebFetch — see `AGENTS.md` and `bench/`.

## Quickstart

```bash
cp .env.example .env   # fill in what you have; unset vars just get skipped
./setup.sh             # Linux (native or WSL2) / macOS
# or, on native Windows:
./setup.ps1
```

Requires [`uv`](https://docs.astral.sh/uv/) - it manages the Python
interpreter and dependencies for this project, so no separate Python
install is needed. `uv run setup` (what the wrapper scripts call) installs
Codegraph and (Linux/macOS only) Lightpanda; registers
whichever MCP servers have their required secret/path set into
`~/.claude.json` (backing it up first); and starts Bifrost. Idempotent - re-run anytime, e.g.
after adding a secret to `.env` (there's no separate "just recheck" or
"just re-merge config" command any more - re-running `./setup.sh` covers
both). Ctrl+C at any point quits cleanly.

Run the test suite (fast unit tests plus a live MCP integration suite)
with `uv run pytest`; `uv run pytest -m "not integration"` skips the live,
token-costing part for routine local work.

It prints what's left for you to do by hand: generate a Bifrost virtual
key and register any servers you'd rather gateway through it, both via the
web UI at http://localhost:8080 (see https://docs.getbifrost.ai).

If this repo has no `CLAUDE.md` yet, you're also asked whether to generate
one now from `CLAUDE_TEMPLATE.md`, filled in from the repo's actual
manifests/scripts/layout rather than a generic template. Say no (or run
non-interactively) to just get the prompt printed for pasting into any
Claude Code session, here or elsewhere. If a `CLAUDE.md` already exists
you're asked whether to refresh it instead (default no); it's only ever
changed after that explicit yes, and only where the repo no longer matches.

## Credit

The CLAUDE.md template embedded in `CLAUDE_TEMPLATE.md` is adapted from
[abhishekray07/claude-md-templates](https://github.com/abhishekray07/claude-md-templates)
and cross-checked against
[centminmod/my-claude-code-setup](https://github.com/centminmod/my-claude-code-setup).

The Obsidian options considered (librarian-mcp, mcp-obsidian, claude-obsidian)
came from
[hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) -
the largest curated list of Claude Code resources (skills, hooks,
statuslines, MCP servers, agent orchestration).
