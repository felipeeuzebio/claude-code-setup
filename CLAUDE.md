# claude-code-setup

Personal Claude Code environment configuration: an MCP gateway (Bifrost), a curated set of MCP servers, and a reusable language-agnostic `CLAUDE.md` starter template. Not an application — a collection of shell/PowerShell setup scripts and config templates for bootstrapping a Claude Code environment on a new machine.

## Stack

- Bash (`setup.sh`, `githooks/commit-msg`, `scripts/*.sh`) for Linux/WSL2/macOS
- PowerShell (`setup.ps1`, `scripts/*.ps1`) for native Windows
- Python (`scripts/merge-mcp-config.py`) for JSON config merging
- Docker Compose for self-hosted Firecrawl
- No package manager / lockfile — this repo has no application runtime of its own

## Structure

- `setup.sh` / `setup.ps1` - one-shot environment setup, idempotent, platform-specific entry points
- `mcp/mcp-servers.json` - standalone MCP server definitions (GitHub, Context7, Firecrawl, Obsidian/librarian-mcp, browser-use, Lightpanda's native MCP server, Codegraph)
- `.env.example` - secrets/flags `setup.sh`/`setup.ps1` read, plus self-hosted Firecrawl's own docker-compose env (copied as-is into that checkout by `scripts/setup-firecrawl.sh`)
- `CLAUDE_TEMPLATE.md` (root) - reusable `CLAUDE.md`-generation prompt, starter structure embedded, that setup.sh offers to run via `claude -p`
- `scripts/` - installer/merge helpers used by `setup.sh`/`setup.ps1`: `ensure-gum.{sh,ps1}`, `merge-mcp-config.py`, `setup-firecrawl.{sh,ps1}`, `verify-env.{sh,ps1}`, `test-mcp.py`
- `githooks/commit-msg` - Conventional Commits enforcement hook, wired via `git config core.hooksPath githooks`
- `AGENTS.md` (root) - why things are configured the way they are; read before changing MCP server choices or script behavior

## Commands

- Run setup (Linux/WSL2/macOS): `./setup.sh`
- Run setup (native Windows): `./setup.ps1`
- Verify local dependencies are on PATH: `./scripts/verify-env.sh` (or `.ps1` on Windows)
- Verify the registered MCP servers actually answer: `python3 scripts/test-mcp.py` (`--list`, `--filter NAME`, `--jobs N`); drives a real `claude -p` session per server, so it costs tokens and takes a few minutes
- Bring up self-hosted Firecrawl only: `./scripts/setup-firecrawl.sh`
- No build step and no linter — there is no application code to compile. `scripts/test-mcp.py` is an integration suite against live MCP servers, not a unit-test suite

## Verification

After changing a script in this repo:

1. Shellcheck any modified `.sh` file: `shellcheck setup.sh scripts/*.sh githooks/commit-msg`
2. Re-run the modified script end-to-end against a scratch copy of the repo when it touches installs or `~/.claude.json` — never against the real checkout, since e.g. `codegraph init` and MCP registration mutate real local state
3. For `githooks/commit-msg` changes, hand-test both an accepting and a rejecting commit message before relying on it
4. After changing anything under `mcp/` or the merge logic, run `python3 scripts/test-mcp.py` — `verify-env.sh` only proves binaries exist, not that a registered server answers
5. When adding a case to `scripts/test-mcp.py`, prove it can fail: point the server entry at a nonexistent binary and confirm it reports FAIL, not PASS. Several prompts are answerable from the model's own knowledge, so a case that never fails is testing nothing

## Conventions

- Commit messages must pass `githooks/commit-msg`: `type: concise summary` (Conventional Commits: feat/fix/refactor/docs/test/chore/perf/ci, ≤72 chars), optional body where every line is a `- ` bullet or a `Token: value` trailer. This hook is enforced locally via `core.hooksPath githooks`, set up by `setup.sh`/`setup.ps1`.
- `.env` (gitignored, copy from `.env.example`) is read by `setup.sh` line-by-line as plain key/value pairs, never `source`d — preserves spaces/backslashes in values like Windows paths and avoids executing `.env` content as shell code.
- MCP servers are only written into `~/.claude.json` once their required secret/path is actually present and valid (e.g. `OBSIDIAN_VAULT_PATH` must be a real directory) — a placeholder or invalid entry is worse than a server that's just not registered yet; missing pieces are listed at the end of the run instead.
- gum (styled terminal output) is strictly cosmetic and never a hard dependency — if missing, it's downloaded to a temp dir for that run only and every gum call has a plain-`printf`/`Write-Host` fallback.
- Setup scripts are idempotent — safe to re-run after adding one more secret to `.env`.
- For the reasoning behind specific tool/server choices (Bifrost vs. alternatives, Codegraph vs. Graphify, librarian-mcp vs. mcp-obsidian, browser-use's `--cli-mcp` mode, etc.), see `AGENTS.md` before changing them — several were arrived at after ruling out non-obvious failure modes.

## Don't

- Don't `source .env` or otherwise eval its contents as shell — read it as plain text (see the `.env` convention above); this previously corrupted Windows-style paths containing spaces/backslashes.
- Don't drop new git hooks into `.git/hooks/` directly — they won't be tracked or cloned; add them under `githooks/` instead so `core.hooksPath` picks them up.
- Don't write an MCP server entry into a config with a placeholder/missing secret — skip it and surface the gap in the run summary instead.
- Don't wrap install/status commands in the `spin`/`Invoke-Spin` helper if they might need interactive input (e.g. a sudo prompt) — the spinner hides output and will hang silently; print the command for the user to run manually instead.
