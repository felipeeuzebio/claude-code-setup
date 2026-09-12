# Setup decisions

Recorded 2026-09-11, capturing the *why* behind this repo's setup choices, not just the *what*.

## Bifrost as the MCP gateway

Bifrost (Maxim AI) was chosen over running each MCP server directly against
Claude Code because it doubles as an LLM gateway (cost/observability across
model calls) and an MCP aggregator (one `/mcp` endpoint fronting every
downstream tool server), in a single self-hostable Go binary. No other
open-source option combines both roles.

Caveat: Bifrost's own docs don't fully spell out the config-file schema for
registering downstream MCP servers — that's done through its web UI
(`http://localhost:8080`, Settings → MCP → Add Server) or management API,
not by hand-editing JSON we control. Re-check `docs.getbifrost.ai` if the
UI has moved things around.

## Firecrawl: self-hosted via Docker, not cloud

Uses Docker Desktop's WSL2 integration rather than Docker Engine natively
in the distro, or Firecrawl Cloud, since Docker Desktop was already the
assumed setup.

Two bugs to know about if `docker compose up` misbehaves on first run,
both worked around in `scripts/setup-firecrawl.sh` / the Firecrawl section
of `.env.example`:

- **RabbitMQ `EACCES` on `.erlang.cookie`** — a known
  Docker-Desktop-on-WSL2 anonymous-volume permission quirk. Fix:
  `docker compose down -v && docker compose up -d` once.
- **`NUQ_BACKEND=postgres` is not a valid value** — the API only accepts
  `pg` or `fdb`. Set to `pg`, matching the `nuq-postgres` service this
  compose file brings up.

Both are WSL2/Docker-Desktop-specific; native Linux with Docker Engine
installed directly hits neither. `setup.sh`'s docker check and
`scripts/setup-firecrawl.sh` are plain `docker compose` calls with no
WSL-specific logic of their own.

## browser-use + Lightpanda: both, not either/or

These aren't competing choices — they sit at different layers:

- **browser-use** gives Claude Code low-level browser control
  (`browser_exec`/`browser_screenshot`, backed by browser-use's Chromium
  "browser harness") for exploratory browsing where you don't already know
  the exact sequence of steps.
- **Lightpanda** is a browser *engine* (CDP-compatible, built from scratch
  in Zig, ~11x faster / ~1/16th the memory of headless Chrome), registered
  via its own native `lightpanda mcp` stdio server (see "Lightpanda behind
  @playwright/mcp did not work" below), for performance-sensitive scripted
  scraping where you already know the steps.

Use browser-use when you'd otherwise write scraping logic by hand; use
Lightpanda's MCP server when you already have a deterministic sequence and
just want it fast and cheap to run repeatedly.

**browser-use's MCP *mode* matters, not just its hosting.** `--mcp` runs
browser-use's own internal autonomous agent, whose LLM client is hardcoded
to `ChatOpenAI` (`browser_use/mcp/server.py`) — it only reads
`OPENAI_API_KEY`, with no generic "bring your own provider" support
despite the underlying library supporting many providers
([docs.browser-use.com/open-source/supported-models](https://docs.browser-use.com/open-source/supported-models));
`LLMEntry` in `browser_use/config.py` has no `base_url` field. The only
other provider wired into `--mcp` is AWS Bedrock (`MODEL_PROVIDER=bedrock`).
Neither fits a self-host-everything setup with no OpenAI/AWS account, so
this uses `--cli-mcp` instead (`browser_use/mcp/cli_mcp.py`) — no internal
agent, no LLM key of any kind: it exposes `browser_exec` (run Python
against a persistent browser session - `new_tab`, `goto_url`, `click_at_xy`,
`js`, `cdp`, etc.) and `browser_screenshot`, and Claude Code itself decides
what to do with them.

Two more gotchas found running this in practice:

- **`uvx browser-use[cli]` needs `--python 3.12` pinned explicitly.**
  browser-use requires Python >=3.11, but `uvx` doesn't reliably pick a
  satisfying interpreter if an older managed one (e.g. a stray 3.10) is
  already on the machine, even when a newer default Python exists
  system-wide. Pinned in `mcp/mcp-servers.json`'s args; `uv` downloads 3.12
  on demand if needed.
- **Chromium install is not something `setup.sh`/`setup.ps1` run for
  you.** `uvx browser-use[cli] install` (needed once, before first use)
  runs `playwright install chromium --with-deps` on Linux, and
  `--with-deps` shells out to `sudo apt-get install` — an interactive sudo
  prompt that a wrapping spinner would hide. Both scripts print the exact
  command to run once, in the final summary, instead of automating it.
  (Windows doesn't hit the sudo case — `--with-deps` is Linux-only.)

## Codegraph over Graphify

Both are codebase-knowledge-graph MCP servers with heavy feature overlap
(symbol graphs, impact analysis, token-budgeted context). Codegraph was
kept because:

- It was already installed locally (`codegraph` CLI) — zero extra install
  cost.
- Broader tool surface (9 MCP tools: search, context, callers/callees,
  impact, explore, node, files, status) versus Graphify's
  graph-analysis-only focus.
- Running both would mean two overlapping graph indexes to keep in sync
  for no added capability.

Ripgrep alone was ruled out as *sufficient* (not as a tool to drop) because
it can't answer structural questions — "who calls this", "what breaks if I
change this" — that Codegraph answers directly from a persisted graph
instead of re-deriving them from text search every time.

**Install flow:** `codegraph install --target claude --location global -y`
prints its own terminal-UI status box on every run, so it's wrapped in the
same `spin`/`Invoke-Spin` helper used elsewhere and replaced with a
one-line "registered" confirmation. After install, `setup.sh`/`setup.ps1`
offer `codegraph init` if `.codegraph/` doesn't exist yet in the current
repo, or `codegraph sync` if it does, rather than codegraph's own generic
"next steps" hint. A non-interactive terminal gets the command printed
instead of being asked.

## Obsidian: librarian-mcp instead of mcp-obsidian

Swapped after checking
[hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code),
the largest curated Claude Code resource list. Went with
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
- Ships native release binaries for Linux, macOS, *and* Windows - no
  OS restriction despite reading the vault straight off disk rather than
  talking to the Obsidian app.

Also considered from the same list but not adopted: `agentcairn`,
`claude-bedrock`, and `claude-obsidian` - all take a more opinionated
"second brain" / Zettelkasten angle than a plain MCP server, more setup
than this needed.

**Path conventions**, since only the filesystem librarian-mcp itself runs
on matters (Obsidian.app doesn't need to be running at all):

- `setup.ps1` (native Windows): a normal Windows path, e.g.
  `C:\Users\you\Documents\MyVault`.
- `setup.sh` under WSL2, vault on the Windows side: use the `/mnt/c/...`
  mount, not the Windows-style path - e.g.
  `/mnt/c/Users/you/Documents/MyVault`. Works, but cross-boundary 9p file
  access is noticeably slower than a native mount; worth knowing if
  running trigram search or graph analytics over a large vault repeatedly.

## setup.sh/setup.ps1: skip rather than write broken entries

Both scripts (and the `scripts/merge-mcp-config.py` they share) only add
an MCP server to `~/.claude.json` once its required secret/path is
present - a silently-broken MCP server is worse than one that's just not
there yet. Missing pieces are listed at the end of the run instead, so
re-running after adding one line to `.env` is the whole fix.

Two things this rule had to be tightened for:

- **"Present" for `OBSIDIAN_VAULT_PATH` means a real directory, not just a
  non-empty string.** A typo'd path, or a Windows-style `C:\...` path
  handed to the WSL2/Linux `librarian-mcp` binary (which needs
  `/mnt/c/...` instead), used to pass a bare `bool(vault_path)` check and
  only fail later at Claude Code runtime as an opaque MCP connection
  error. `build_plan()` in `scripts/merge-mcp-config.py` now checks
  `Path(vault_path).is_dir()`; `setup.sh`/`setup.ps1` run the same check
  inline so the warning shows up during the run itself. Lightpanda is
  Linux/macOS-only, so `setup.ps1` skips it outright rather than
  half-installing.
- **`setup.sh`'s own `.env` loader used to corrupt paths with spaces.** It
  `source`d `.env` directly, but `source` runs it as real bash: an
  unquoted value with a space (a Windows-style
  `OBSIDIAN_VAULT_PATH=C:\Users\you\Documents\My Vault`) gets word-split,
  and backslashes get interpreted as shell escapes and silently stripped.
  `setup.sh` now reads `.env` line-by-line with plain string ops
  (`${line%%=*}` / `${line#*=}`) and `export`s each key directly, never
  evaluating the value as shell code. `setup.ps1` never had this bug -
  `Get-Content`/`.Split('=')` is plain text splitting, not code execution.

## CLAUDE.md init: an interactive setup-time ask, not an installed command

Considered a `/init-claude-md` slash command installed into
`~/.claude/commands/`, but the actual want was narrower: ask once, at
setup time, whether to generate this repo's `CLAUDE.md` now, and if not
(or the run is non-interactive), just print the prompt so it can be pasted
into any Claude Code session whenever it's wanted. That doesn't need a
permanently-installed command:

- `CLAUDE_TEMPLATE.md` (root) holds the prompt text with the starter
  structure embedded, no slash-command frontmatter - just a prompt, read
  by the setup scripts and cat-able by a human.
- If `CLAUDE.md` already exists, the step is skipped outright - it never
  overwrites hand-written project knowledge. The "yes" path also tells the
  model to summarize changes and wait for confirmation if the file somehow
  is present, as a second guard.
- A non-interactive run (no TTY on stdin) never blocks on a prompt - it
  prints the copy-paste block, same as answering no.
- Saying yes runs `claude -p "$(cat CLAUDE_TEMPLATE.md)"` right there,
  since setup.sh/setup.ps1 already `cd` to the repo root before this step.

## Gum styling

setup.sh/setup.ps1 style their output with
[gum](https://github.com/charmbracelet/gum), strictly as a cosmetic layer:

- If gum is already on PATH, it's used untouched. If not,
  `scripts/ensure-gum.sh`/`.ps1` download the matching release binary into
  a `mktemp -d` for that run only, removed on exit (`trap ... EXIT` /
  `finally`) - nothing is ever installed system-wide.
- Every gum call is guarded by "if $GUM is set"; a failed download
  (offline, unsupported OS/arch) falls back to plain
  `printf`/`Write-Host` output rather than aborting setup.
- Styling is a single foreground color per line, no borders/boxes/bold -
  anything louder (a `--border rounded --padding` box originally around
  the final summary, `--margin` for blank lines) added no information.
- `gum spin` passes `--spinner line` (plain ASCII `| / - \`) instead of
  the default `dot` spinner, whose frames are Braille Pattern Unicode
  characters that render as mangled boxes on fonts without full coverage
  (common on stock Windows Terminal/WSL2).

**Ctrl+C during `gum confirm`/`gum spin` doesn't behave like a normal
SIGINT.** gum's TUI puts the terminal in raw mode, so Ctrl+C there is a
keystroke gum itself interprets (exit code 130) rather than an actual
signal delivered to the shell - left unhandled, the script would treat it
as "answered no" or "that install failed" and continue. Every
`gum confirm`/`gum spin` call checks for exit code 130 specifically and
calls `quit_setup`/`Stop-Setup`, which prints "Setup cancelled." and exits
130 itself, triggering the same cleanup trap that removes a
temp-downloaded gum. Plain-fallback mode (no gum) needed no such handling
- a real terminal `read`/`Read-Host` already receives a real SIGINT.

## Commit message convention enforced via a commit-msg hook, not pre-commit

Enforces `type: concise summary` (Conventional Commits:
feat/fix/refactor/docs/test/chore/perf/ci, ≤72 chars, `type(scope):`
accepted) plus, if a body is present, every line must be a `- ` bullet or
a trailer (`Co-Authored-By: ...`-style `Token: value` lines are exempt
from the bullet rule).

This has to be a **commit-msg** hook, not pre-commit - pre-commit runs
before the commit message is written and is never given it as an
argument, so it structurally cannot validate message content. commit-msg
receives the message's temp file path as `$1` and can reject the commit
by exiting non-zero.

The script lives at `githooks/commit-msg`, tracked in the repo, rather
than `.git/hooks/` - hooks placed there aren't committed or cloned, so
every clone would silently have no enforcement. `git config
core.hooksPath githooks` points git at the tracked directory instead;
`setup.sh`/`setup.ps1` run that config command as their first step so
it's wired up automatically on setup.

## Repo: private

The repo stores MCP server topology and setup scripts referencing personal
services (self-hosted Firecrawl, Obsidian vault, Bifrost instance). Kept
private by default; secrets themselves are never committed (see
`mcp/mcp-servers.json` placeholders) so it could be made public later
after a final scan.

## MCP servers are tested by driving a real `claude -p` session

`scripts/verify-env.sh` only proves binaries are on PATH. That says
nothing about whether a *registered* MCP server actually answers, so
`scripts/test-mcp.py` drives a real `claude -p --model sonnet` session per
server and checks the result.

The hard part: most of these prompts can be answered *without* the server
under test - the model already knows what octocat/Hello-World's README
says, and can reach a URL with WebFetch. A naive harness would go green
against a completely dead server (pointing the GitHub case at a
nonexistent binary confirms this: it fails at layer 1 rather than passing
from the model's own knowledge). So every case is validated in three
independent layers:

1. **connected** - the server's tools appear in the session's `init` event
2. **invoked** - the expected tool shows up as a real `tool_use` in the
   transcript
3. **correct** - the final answer matches an expected pattern

Each case runs with `--strict-mcp-config` (only the server under test), a
tool allowlist, and an explicit denylist of
WebFetch/WebSearch/Bash/Read/Glob/Grep.

Test pages were chosen to be stable and to have a *discriminating*
answer:

- `example.com` - IANA-maintained, reserved by RFC 2606. Assertions use
  the `Example Domain` heading, not the body copy, which is not stable
  over time.
- `quotes.toscrape.com/js/` - Zyte's scraping sandbox, published for
  exactly this purpose. Its quote list is built from a `var data = [...]`
  array by JavaScript, so a JS-executing browser sees 10 `.quote`
  elements and a plain HTTP fetch sees 0 - the single number that
  separates a real headless browser from a bare fetch, which is why it
  backs the Firecrawl, browser-use, and Lightpanda cases.
- `octocat/Hello-World` - the canonical GitHub test repo; its `README` has
  read `Hello World!` since 2011.
- Context7 asserts on the registry-assigned ID `/colinhacks/zod`, which
  the model cannot plausibly produce without a real lookup.

Cases skip (rather than fail) when a server isn't registered or a
prerequisite is missing, so the suite stays meaningful on a partial setup.
The Obsidian case is deliberately read-only (`library_stats`) - a test
must never write into someone's real vault.

## Lightpanda behind @playwright/mcp did not work - switched to its native MCP server

`scripts/test-mcp.py` found the `lightpanda-playwright` server
(`@playwright/mcp` driven over `--cdp-endpoint`) to be broken. Two
separate causes:

1. `--cdp-endpoint ws://localhost:9222` never completes the WebSocket
   handshake, while `ws://127.0.0.1:9222` connects immediately - fixed in
   `mcp/mcp-servers.json`. Lightpanda rejects any upgrade request carrying
   an `Origin` header with a 403, which is the likely mechanism.
2. With the connection fixed, navigation still times out. Playwright
   waits for a `Page.lifecycleEvent`/`frameStoppedLoading` after
   `Page.navigate`; Lightpanda 1.0.0-nightly answers the `Page.navigate`
   command but emits no such event, so every `goto` hangs regardless of
   `waitUntil`. Reproduced with playwright-core 1.59, 1.62, and 1.63, and
   by speaking raw CDP directly.

Lightpanda itself is fine - its own `lightpanda mcp` stdio server
navigates and evaluates correctly (`evaluate` with `{url, script}` on the
JS quotes page returns `10`), needs no separate `serve` process, no port,
and no `@playwright/mcp` dependency, and exposes a richer surface (`tree`,
`markdown`, `html`, `findElement`, `evaluate`, `extract`, form/DOM tools,
sessions).

`mcp/mcp-servers.json`'s `lightpanda-playwright` entry has been replaced
with `lightpanda` (`command: lightpanda`, `args: ["mcp"]`), and
`scripts/test-mcp.py`'s case now drives `evaluate` directly. This does
change the tool surface agents see (different tool names, a text/DOM-
oriented model instead of the standard Playwright MCP surface) - accepted
since the Playwright-over-CDP path cannot be made to work against
Lightpanda at all, not just inconvenient to use.

## browser-use needs a browser already running

`browser-use --cli-mcp` attaches to a running Chromium-family browser; it
never launches one. On a headless box nothing is running, so every call
fails with `chrome-not-running`, even though `setup.sh` installs Chromium.

Its discovery probes only ports 9222 and 9223, and 9222 is where
Lightpanda listens - which browser-use correctly refuses, since Lightpanda
is not a Chromium-family browser. The reliable fix is the documented
`BU_CDP_URL` override: `http://127.0.0.1:9223` is stable, whereas
`BU_CDP_WS` embeds a per-launch browser UUID. `scripts/test-mcp.py` starts
a headless Chromium on 9223 when nothing is there and injects
`BU_CDP_URL` into the server entry for the test session only.
