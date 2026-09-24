# claude-code-setup

Personal Claude Code environment configuration: an MCP gateway (Bifrost), a curated set of MCP servers, and a reusable language-agnostic `CLAUDE.md` starter template. Not an application in the usual sense — a `uv`-managed Python package (`src/claude_code_setup/`) that bootstraps a Claude Code environment on a new machine, invoked through two thin shell/PowerShell wrapper scripts.

## Stack

- Python, run via `uv` (`uv run setup`) — no separate Python install needed, `uv` manages the interpreter
- `rich` is the one runtime dependency (styled terminal output); `pytest` + `pytest-xdist` are dev-only
- Bash (`setup.sh`, `githooks/commit-msg`) for Linux/WSL2/macOS — both are thin, `githooks/commit-msg` is a standalone hook unrelated to the Python package
- PowerShell (`setup.ps1`) for native Windows — same thin-wrapper shape
- `pyproject.toml` + `uv.lock` — no other build step; this package is never published or installed elsewhere, only run in-place via `uv run`

## Structure

- `setup.sh` / `setup.ps1` - thin wrappers: check `uv` is present, `exec uv run setup`
- `install.sh` / `install.ps1` - one-line bootstraps (`curl … | bash` / `irm … | iex`): install `uv` if missing, download the repo tarball/zip from GitHub into `~/.claude-code-setup` (keeping its `.env`/`.codegraph/` across re-runs, leaving a git checkout alone), then run `setup.sh`/`setup.ps1` against the directory they were launched from. The repo slug is hardcoded in both
- `src/claude_code_setup/` - the actual logic, a `uv`-managed packaged app:
  - `__init__.py` - package marker, nothing else
  - `main.py` - orchestration spine (`main()`), what `uv run setup` (a `[project.scripts]` entry, `claude_code_setup.main:main`) calls
  - `mcptest` lives in `tests/`, not here - it's test code, not part of the shipped tool
  - `core/` - helpers every step uses: `ui.py` (terminal output), `envfile.py` (`.env` parsing), `sysinfo.py` (tool detection)
  - `mcp/` - `servers.py` (loads `mcp-servers.json`, defines `REPO_ROOT`) and `config.py` (merges ready servers into `~/.claude.json`)
  - `claudemd.py`, `bifrost.py` - the CLAUDE.md and Bifrost steps. The CLAUDE.md step targets the launch dir (`CLAUDE_CODE_SETUP_PROJECT_DIR`, set by the wrappers): an existing root `CLAUDE.md`, else `.claude/CLAUDE.md`
  - everything except `main.py` is internal-only: plain functions `main.py` imports, no standalone entry point
- `tests/` - `pytest` suite, a package (`uv run pytest`): `test_envfile.py`/`test_mcpconfig.py`/`test_claudemd.py`/`test_main.py` are fast fixture-based unit tests; `test_mcp_servers.py` + `conftest.py` are the live MCP integration suite, marked `integration` (`uv run pytest -m "not integration"` skips it)
- `mcp-servers.json` (root) - standalone MCP server definitions (GitHub, Context7, browser-use, Lightpanda's native MCP server, Codegraph, dbx)
- `.env.example` - secrets/flags `setup` reads
- `CLAUDE_TEMPLATE.md` (root) - reusable `CLAUDE.md`-generation prompt, starter structure embedded, that `setup` offers to run via `claude -p` (generate if missing, refresh after a y/n if present; no `--model` pin, the user's default model is the point)
- `githooks/commit-msg` - Conventional Commits enforcement hook (plain bash, out of scope of the Python package), wired via `git config core.hooksPath githooks`
- `AGENTS.md` (root) - why things are configured the way they are; read before changing MCP server choices or script behavior
- `bench/` - the measurements behind those choices, as a package: `harness.py` (shared `claude -p` session runner) plus one subpackage per bench with its harness and a `results.md` write-up. Not part of `pytest`; run as `uv run python -m bench.<folder>.<script>`, costs real tokens

## Commands

- Run setup (Linux/WSL2/macOS): `./setup.sh` (run from the project whose CLAUDE.md you want)
- Run setup (native Windows): `./setup.ps1`
- One-line install, no clone: `curl -fsSL https://raw.githubusercontent.com/felipeeuzebio/claude-code-setup/main/install.sh | bash` / `irm https://raw.githubusercontent.com/felipeeuzebio/claude-code-setup/main/install.ps1 | iex`
- Run the whole test suite (fast unit tests + live MCP integration suite): `uv run pytest`
- Fast subset only (no network, no tokens spent): `uv run pytest -m "not integration"`
- Just the MCP integration suite: `uv run pytest -m integration` (or `-k <name>` for one case; `-n N` for concurrency via `pytest-xdist`; `--model`/`--mcp-timeout` to override defaults; `--collect-only -q` to list cases)
- There's no standalone "just verify tools" or "just re-merge config" command any more - re-run `./setup.sh` (idempotent) instead
- No build step and no linter configured yet — `pyproject.toml` has no `[project.scripts]` beyond `setup`, and nothing here is published or installed elsewhere
- Benches: `uv run python -m bench.web_tools.webtools`, `uv run python -m bench.docs_retrieval.threearm`, `uv run python -m bench.vault_plugin.trial` — each runs ~20 live `claude -p` sessions, takes minutes, costs real tokens; see `bench/README.md`

## Verification

After changing anything in this repo:

1. For changes under `src/claude_code_setup/` or `tests/`: run `uv run pytest -m "not integration"` (fast) and, when touching MCP registration/test logic specifically, the full `uv run pytest` (costs tokens, drives real `claude -p` sessions)
2. Re-run `./setup.sh`/`./setup.ps1` end-to-end against a scratch copy of the repo when a change touches installs or `~/.claude.json` — never against the real checkout, since e.g. `codegraph init` and MCP registration mutate real local state
3. For `install.sh`/`install.ps1` changes: run a copy with the final `setup` call stubbed out and `CLAUDE_CODE_SETUP_DIR` pointed at a scratch dir, piped through `bash`/`iex` (that's how users run them), twice - the second run must keep `.env`
4. For `githooks/commit-msg` changes (a plain bash script, untouched by the Python rewrite), hand-test both an accepting and a rejecting commit message before relying on it
5. When adding a case to `tests/test_mcp_servers.py`, prove it can fail: point the server entry at a nonexistent binary and confirm it reports FAIL, not PASS/SKIP. Several prompts are answerable from the model's own knowledge, so a case that never fails is testing nothing

## Conventions

- Commit messages must pass `githooks/commit-msg`: `type: concise summary` (Conventional Commits: feat/fix/refactor/docs/test/chore/perf/ci, ≤72 chars), optional body where every line is a `- ` bullet or a `Token: value` trailer. This hook is enforced locally via `core.hooksPath githooks`, set up by `setup.sh`/`setup.ps1`.
- `.env` (gitignored, copy from `.env.example`) is read by `src/claude_code_setup/core/envfile.py` line-by-line as plain key/value pairs, never evaluated as shell/Python — preserves spaces/backslashes in values like Windows paths.
- MCP servers are only written into `~/.claude.json` once their required secret is actually present and valid (e.g. `GITHUB_TOKEN`) — a placeholder or invalid entry is worse than a server that's just not registered yet; missing pieces are listed at the end of the run instead.
- `setup` maintains a marker-delimited (`<!-- WEB_TOOLS_START -->`) block in the user's global `~/.claude/CLAUDE.md` routing web lookups: built-in WebSearch/WebFetch first, Context7 for library docs, Lightpanda/browser-use only as escalation (order measured in `bench/`). Only the block is rewritten, and only servers that actually registered get a bullet — see `AGENTS.md` before changing the wording or the gating.
- Terminal output goes through `src/claude_code_setup/core/ui.py` (built on `rich`) — colored ok/skip/warn/step lines, a spinner, a y/n confirm, Markdown rendering. No external binary (gum was dropped entirely during the Python rewrite).
- Setup is idempotent — safe to re-run `./setup.sh`/`.ps1` after adding one more secret to `.env`; it's also the only way to re-check tool status or re-merge MCP config now (no separate standalone commands for those).
- For the reasoning behind specific tool/server choices (Bifrost vs. alternatives, Codegraph vs. Graphify, why there's no Obsidian vault tool yet, browser-use's `--cli-mcp` mode, etc.), see `AGENTS.md` before changing them — several were arrived at after ruling out non-obvious failure modes.

## Don't

- Don't parse `.env` as shell or Python source — read it as plain text (see the `.env` convention above); an earlier bash version that `source`d it corrupted Windows-style paths containing spaces/backslashes.
- Don't drop new git hooks into `.git/hooks/` directly — they won't be tracked or cloned; add them under `githooks/` instead so `core.hooksPath` picks them up.
- Don't write an MCP server entry into a config with a placeholder/missing secret — skip it and surface the gap in the run summary instead.
- Don't re-add Firecrawl (or any scraping server) to the default web-tool path on the strength of features — it was removed on measurement (`bench/web_tools`, `AGENTS.md`); a new server earns a `WEB_TOOLS` bullet by beating the built-ins on a bench, and Firecrawl Cloud, if ever wanted, goes in gated on `FIRECRAWL_API_KEY` like every other secret-bearing server.
- Don't wrap install/status commands in `ui.spin()` if they might need interactive input (e.g. a sudo prompt) — the spinner would hide the prompt on a TTY; run those directly and let output flow through instead.
- Don't add a standalone entry point for `core/sysinfo.py`, `mcp/config.py`, `claudemd.py`, or `bifrost.py` — they're deliberately internal-only, called by `setup`'s `main()`. Only `setup` itself and the `tests/` suite are meant to be run directly.
- Don't put dynamic/interpolated text straight into a `ui.console.print(...)` call without `rich.markup.escape()` — `Console.print` treats `[...]` as style markup by default, so literal brackets (e.g. `browser-use[cli]`) silently vanish otherwise. `ui.ok`/`warn`/`skip`/`step`/`ok_ver`/`confirm` already escape internally; only raw `ui.console.print()` calls need it explicitly.
