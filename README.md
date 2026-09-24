# claude-code-setup

My Claude Code setup: the MCP servers I use, the Bifrost gateway, and a
`CLAUDE.md` template I reuse across projects. One script installs all of it
on a new machine.

## Install

Linux, WSL2 or macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/felipeeuzebio/claude-code-setup/main/install.sh | bash
```

Windows:

```powershell
irm https://raw.githubusercontent.com/felipeeuzebio/claude-code-setup/main/install.ps1 | iex
```

Run it from inside the project you want a `CLAUDE.md` for. It installs `uv`
if you don't have it, downloads the repo to `~/.claude-code-setup` and runs
the setup, which first asks whether you want the full setup or just the
`CLAUDE.md`. To skip the question and only do the `CLAUDE.md`:

```bash
curl -fsSL https://raw.githubusercontent.com/felipeeuzebio/claude-code-setup/main/install.sh | bash -s -- --claude-md-only
```

Run the same line again to update; your `.env` is kept.

Secrets go in `~/.claude-code-setup/.env` (copy `.env.example`), or inline:
`GITHUB_TOKEN=... bash` at the end of the curl line. Anything missing is
skipped and listed at the end.

Set `CLAUDE_CODE_SETUP_DIR` to install somewhere else, or
`CLAUDE_CODE_SETUP_REF` to pick a branch or tag.

If you already have a clone:

```bash
cd ~/some-project
~/claude-code-setup/setup.sh      # or setup.ps1 on Windows; --claude-md-only for just that step
```

## What setup does

- Installs Codegraph, and Lightpanda on Linux/macOS
- Adds the MCP servers below to `~/.claude.json` (after backing it up). A
  server that needs a secret is only added once the secret is set
- Asks before adding a short web-tools section to `~/.claude/CLAUDE.md`
- Starts Bifrost on http://localhost:8080

Running it again is safe, so re-run it whenever you add a secret.

Two things are left to do by hand, and setup reminds you of both: create a
Bifrost virtual key in its web UI, and add any servers you want to go
through the gateway ([Bifrost docs](https://docs.getbifrost.ai)).

It also offers to generate or refresh the `CLAUDE.md` of the project you ran
it from, using `CLAUDE_TEMPLATE.md`. An existing root `CLAUDE.md` is refreshed
in place; otherwise it writes `.claude/CLAUDE.md`. Run from your home dir,
it skips this step. Answer no and it prints the prompt instead, so you can
paste it into Claude Code in any project.

## MCP servers

| Server | What for | Needs |
|---|---|---|
| GitHub | repos, issues, PRs | `GITHUB_TOKEN` |
| Context7 | up-to-date library docs | nothing |
| browser-use | full browser control (clicks, logins) | `uvx` |
| Lightpanda | light headless browser for reading pages | Linux/macOS (WSL2 on Windows) |
| Codegraph | code graph: callers, callees, impact | installed by setup |

I tried Graphify, self-hosted Firecrawl and the Obsidian servers and left
them out. `AGENTS.md` explains why and `bench/` has the measurements.

## Repo layout

```
install.sh, install.ps1   one-line installers
setup.sh, setup.ps1       run `uv run setup`
src/claude_code_setup/    the setup code (Python)
tests/                    pytest suite
mcp-servers.json          MCP server definitions
CLAUDE_TEMPLATE.md        prompt for generating a CLAUDE.md
AGENTS.md                 reasons behind the tool choices
bench/                    benchmarks behind those choices
githooks/                 commit-msg hook (Conventional Commits)
.env.example              secrets and flags
```

## Tests

```bash
uv run pytest -m "not integration"   # quick, offline
uv run pytest                        # also runs live Claude sessions, costs tokens
```

## Credit

The `CLAUDE.md` template is adapted from
[abhishekray07/claude-md-templates](https://github.com/abhishekray07/claude-md-templates)
and checked against
[centminmod/my-claude-code-setup](https://github.com/centminmod/my-claude-code-setup).
The Obsidian options I tried came from
[hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code).
