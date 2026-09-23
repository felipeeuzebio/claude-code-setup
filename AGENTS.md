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

## Firecrawl: removed 2026-09-16, on measurement

Firecrawl was self-hosted here (Docker Compose, ~10 containers) as the
preferred scraping/search server from 2026-09-11 until it was benchmarked
against Claude Code's built-in WebSearch/WebFetch and against Lightpanda
(`bench/web_tools/results.md`). What the numbers said:

- On a **static page**, built-in WebFetch was correct and 5-40x cheaper in
  tokens (53 B vs 624 B; 184 B vs 7,510 B into context) and faster
  (8.5-9 s vs 11-15 s). WebFetch returns a side-model summary rather than
  the page, which is why it's so cheap - and why it's lossy.
- On a **JS-rendered page**, WebFetch fails (no JavaScript) - it burned 6
  calls and 51 s and then guessed. Firecrawl, Lightpanda and browser-use
  all answered in 1-2 calls, 10-16 s. So a JS-capable tool is needed, but
  Lightpanda covers it as a single binary.
- On **plain search**, WebSearch matched `firecrawl_search` on correctness,
  smaller (2.0 vs 2.7 KB) and faster (13 vs 19 s).
- On **library docs** (`bench/docs_retrieval`), Context7 beat a live
  Firecrawl search ~5x on tokens (5.6 KB vs 26.4 KB per question) with
  identical correctness, because it returns passages and Firecrawl returns
  whole pages.
- On **verbatim content** (`bench/web_tools/verbatim.py` - exact quote,
  install command, code line, a setting on a 420 KB reference page), the
  worry that WebFetch's summary would paraphrase did not materialise: 4/4
  exact, 223-546 bytes each. The 420 KB page is where Firecrawl fell
  apart instead - a truncated scrape, then 22 calls, 228 s and 2.1M
  cached tokens of thrashing through its other tools to recover.

What was *not* measured: `crawl` and schema-driven `extract` - the
multi-page/structured features (`map` only appeared as part of the V4
thrash). The removal is not a verdict on those; it
is that nothing in daily use needed them, Claude can do schema extraction
itself from Lightpanda's markdown, and the stack's operational cost was
real and recurring: it did not come back after a WSL reboot, and a server
the global CLAUDE.md says to "prefer" while it is dead costs a failed tool
call on every lookup routed to it. It also registered 27 tool names into
every session. A four-voice council (`/council`) reached the same
conclusion unanimously.

Two consequences to keep in mind:

- **`mcpconfig.merge_and_write()` is additive** - it never removes a
  server from `~/.claude.json`. Dropping one from `mcp-servers.json` leaves
  the old entry in place until it's removed by hand
  (`claude mcp remove firecrawl -s user`). Worth remembering for any future
  removal.
- **If Firecrawl ever comes back, it's Cloud, gated on `FIRECRAWL_API_KEY`**
  under the "no secret, no registration" rule, and it does not get a
  `WEB_TOOLS` bullet without beating the built-ins on a bench. The
  self-hosted bring-up code (`src/setup/firecrawl.py`, the compose env in
  `.env.example`, two Docker-Desktop-on-WSL2 workarounds) is in git history
  before this date.

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
  system-wide. Pinned in `mcp-servers.json`'s args; `uv` downloads 3.12
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

## Obsidian: out of setup for now (librarian-mcp removed 2026-09-16)

`setup` no longer configures anything for an Obsidian vault - no server,
no `OBSIDIAN_VAULT_PATH`, no CLAUDE.md block. The question of how Claude
should reach the vault is parked, to be studied properly later; what
follows is the record of what was tried so that study doesn't start from
zero. The one measured conclusion worth carrying: the vault is a
directory, and one built-in Grep/Read/Write call per operation was cheaper
than every server or plugin tried (turn count sets the token bill, see
`bench/`). A future setup step probably grants access to that directory
(`permissions.additionalDirectories`) and tells Claude it exists in the
global `CLAUDE.md` - a fresh session never looked there unprompted (0/8 in
the docs probe) - rather than registering a server. Inside Obsidian
itself, [Claudian](https://github.com/YishenTu/claudian) (community
plugin, 15k stars) embeds Claude Code with the vault as cwd; on this
machine that is the *Windows* `claude.exe` with its own `~/.claude.json`.

What was tried and why each lost:

- **librarian-mcp** (the previous choice, from
  [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)):
  reads the vault off disk with 17 tools, trigram search, graph analytics.
  In use: 29 stars, no push since 2026-06; indexes once per process with
  no refresh (`/clear` and `/mcp` don't respawn it, killing the process
  does); multi-word `library_search` returns empty snippets and no phrase
  match, so Claude ranks hits by filename; `library_read` is whole-page
  only. At 188 notes / 2 MB there is nothing for its index to speed up
  that Grep doesn't do in one call.
- **mcp-obsidian** (`MarkusPfundstein`, 4.4k stars): seven tools over the
  Obsidian *Local REST API* plugin - needs Obsidian running, that plugin
  installed, an `OBSIDIAN_API_KEY` and a self-signed cert; `mcp` SDK
  pinned `<2.0`. Mirrored WSL networking would make `localhost:27124`
  reachable, so it *would* work; it just buys a running-app dependency and
  a secret for read/search/append the built-ins already have. Its one
  extra, `patch_content` under a heading, is an `Edit` with `old_string`.
- **@modelcontextprotocol/server-filesystem**: read/write/edit/list/move
  and `search_files`, which is a **glob on names, not content**. A strict
  subset of the built-in tools, minus Grep, one ToolSearch further away.
- **claude-obsidian** (Claude Code plugin, v2.2.0, 15k stars) - measured
  in `bench/vault_plugin/results.md`: good BM25 retrieval (8/8 bench pages
  in the top 3, real snippets) and transactional writes with provenance,
  but its writes fail on a vault under `/mnt/c` (enforces file mode
  `0600`, drvfs reports `0777` -> `RESULT_DRIFT`, rolled back), it only
  indexes `wiki/` so it dictates the layout, and its skills drive a Python
  CLI turn by turn (starting with `find /` for its own install path):
  5-30x librarian-mcp per operation. Revisit only if the vault moves to a
  filesystem where its writes succeed *and* a release resolves its own
  product root.

**Path conventions** for whenever a vault path comes back, since only the
filesystem the Claude Code process runs on matters (Obsidian doesn't need
to be running):

- `setup.ps1` (native Windows): a normal Windows path, e.g.
  `C:\Users\you\Documents\MyVault`.
- `setup.sh` under WSL2, vault on the Windows side: the `/mnt/c/...` mount,
  not the Windows-style path - e.g. `/mnt/c/Users/you/Documents/MyVault`.
  Cross-boundary 9p access is slower than a native mount and does not
  honour POSIX file modes (everything is `0777` without the `metadata`
  automount option) - harmless for Grep/Read/Write, fatal for tools that
  verify modes after writing.

## setup: skip rather than write broken entries

**2026-09 update:** `setup.sh`/`setup.ps1` are now thin wrappers around a
`uv`-managed Python package (`src/claude_code_setup/`) - see `CLAUDE.md` for the
current structure. The reasoning below still holds; only the file paths
it names have moved.

`setup`'s `mcp/config.py` (called from `main()`, not a standalone script
any more) only adds an MCP server to `~/.claude.json` once its required
secret/path is present - a silently-broken MCP server is worse than one
that's just not there yet. Missing pieces are listed at the end of the
run instead, so re-running `./setup.sh`/`.ps1` after adding one line to
`.env` is the whole fix.

Two things this rule had to be tightened for:

- **"Present" means valid, not just non-empty.** When `OBSIDIAN_VAULT_PATH`
  was a thing, a typo'd path or a Windows-style `C:\...` path handed to a
  WSL2/Linux process (which needs `/mnt/c/...`) used to pass a bare
  `bool(value)` check and only fail later at Claude Code runtime as an
  opaque MCP connection error; the fix was `Path(value).is_dir()` before
  writing anything. Same principle for any path-shaped secret that comes
  back. Lightpanda is Linux/macOS-only, so the
  Windows path skips it outright rather than half-installing.
- **The original bash `setup.sh`'s own `.env` loader used to corrupt paths
  with spaces.** It `source`d `.env` directly, but `source` runs it as
  real bash: an unquoted value with a space (a Windows-style
  `OBSIDIAN_VAULT_PATH=C:\Users\you\Documents\My Vault`) gets word-split,
  and backslashes get interpreted as shell escapes and silently stripped.
  This is exactly why `src/claude_code_setup/core/envfile.py` never evaluates `.env` as
  shell/Python - it's a plain line-by-line parser that only strips one
  matching layer of quotes, preserving everything else byte-for-byte.

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
- If `CLAUDE.md` already exists, setup asks whether to *refresh* it
  (default no) instead of skipping. The template tells the model to
  summarize and wait for confirmation when the file is present, but
  `claude -p` can't ask, so the y/n happens in the terminal and
  `REFRESH_LEAD` hands the answer over: keep every hand-written line that
  still matches the repo, change only what no longer does. Nothing is
  overwritten without that explicit yes, and a non-interactive run never
  touches an existing file. Review with `git diff CLAUDE.md` afterwards.
- No `--model` is passed to `claude -p` on purpose: the file should come
  from whatever the user's default model is, not a pin that goes stale.
- A non-interactive run (no TTY on stdin) never blocks on a prompt - it
  prints the copy-paste block, same as answering no.
- Saying yes runs `claude -p "$(cat CLAUDE_TEMPLATE.md)"` right there,
  since setup.sh/setup.ps1 already `cd` to the repo root before this step.

## Web tool guidance lives in the global CLAUDE.md, gated on what registered

Registering an MCP server makes its tools *available*, not *preferred*:
each server ships its own instructions, but those describe the server in
isolation and can't say "use this instead of WebFetch" - or the reverse.
The integration suite hides this, because every case runs with
WebFetch/WebSearch/Bash explicitly denied (see the testing section below),
so it proves the servers *work*, never that they'd be *chosen*.

So `setup` maintains a `<!-- WEB_TOOLS_START -->`-delimited block in the
user's global `~/.claude/CLAUDE.md` - the same marker shape codegraph's own
installer uses there, and global rather than per-project because tool
routing isn't project-specific (`CLAUDE_TEMPLATE.md` deliberately stays
about the repo being documented).

**The block's order is measured, not assumed.** The first version (2026-09)
said "prefer Firecrawl/Lightpanda/browser-use over WebFetch/WebSearch".
`bench/web_tools` then showed that steers every trivial lookup onto the
heaviest tool: built-in WebFetch/WebSearch win on a static page and a
plain search, and only lose when the page needs JavaScript (see the
Firecrawl section above). The block now says: built-ins first; Context7
before any web tool for library docs; Lightpanda as the escalation for
JS-rendered pages or verbatim page content; browser-use only for real
interaction. `tests/test_claudemd.py` pins that order. Change the wording
only with a bench result in hand.

Two properties worth preserving:

- **Gated on what actually registered.** `merge_and_write()` returns its
  registered list and the block is rendered from that, so a machine without
  Lightpanda never gets a bullet recommending it. Same reasoning as "skip
  rather than write broken entries" above - advice pointing at an absent
  tool is worse than no advice. A run that registers none of them removes
  the block instead of leaving it stale.
- **Only the marked block is rewritten.** Everything outside the markers is
  hand-written and left byte-identical; a re-run with the same servers is a
  no-op, which is what keeps `./setup.sh` safely idempotent here.

## Docs are not mirrored into the vault (probe, 2026-09-15)

The idea: crawl documentation sites into the Obsidian vault
(`Indexed Docs/<docname>/<version>/<page-slug>.md`) so lookups become local
`library_search` -> `library_read` reads. A Stage-0 probe built the crawler
(`docs-index`, since deleted - in git history), mirrored Drizzle ORM (187
pages, 8 min, zero context tokens) and ran 8 questions through three arms
(`bench/docs_retrieval/results.md`). All three arms were 8/8 correct;
Context7 cost 5.6 KB per question against the vault's 13.8 KB, because
`library_read` returns whole pages and has no section/range option. The
vault did beat a live Firecrawl search 2x on tokens and latency - but
that niche (docs Context7 doesn't cover) never came up in practice, so the
crawler was removed with Firecrawl rather than kept as dead weight. Three
things learned about librarian-mcp (since removed - see the Obsidian
section) that still matter for any vault tool:

- **It indexes once, at process start, and has no refresh tool.** Each
  Claude Code conversation spawns its own `librarian-mcp` (child of that
  `claude` process); `/clear` and `/mcp` do *not* respawn it. Killing the
  process does - Claude Code lazily respawns it on the next tool call with
  context intact. Any file written to the vault from outside a session is
  invisible to that session until then.
- **Multi-word `library_search` queries return empty snippets and do no
  phrase matching** (bag-of-words scoring); single-word queries return
  snippets. Claude ends up ranking hits by filename, so readable note
  names matter more than they look.
- In a fresh session, nothing told Claude the vault held docs: it never
  looked there (0/8) without an explicit hint. Tool selection is driven by
  prompt text, not tool quality - the reason the `WEB_TOOLS` block exists.

## bench/: measurements behind these decisions

`bench/` holds the harnesses and write-ups the two sections above rest
on. `bench/harness.py` runs one `claude -p` session locked to a given set
of MCP servers and tools (same technique as the integration suite) and
records correctness, tool calls, bytes returned by tools, the session's
own `usage`, and wall-clock. Each bench folder is a script plus
`results.md`; raw `results.jsonl` is regenerated per run and gitignored.
Not part of `pytest` - they cost real tokens. One lesson from running
them: **turn count dominates total tokens.** Every turn re-reads ~100k
cached tokens of system prompt and tool schemas, so one extra tool call
outweighs several KB of tool output; compare arms on calls first.

## Gum styling (superseded 2026-09 - kept for history)

Originally, `setup.sh`/`setup.ps1` styled their output with
[gum](https://github.com/charmbracelet/gum), strictly as a cosmetic layer.
During the 2026-09 Python rewrite, gum was dropped entirely in favor of
`rich` (`src/claude_code_setup/core/ui.py`) - no external binary, no download/temp-dir
lifecycle, and it restores Markdown rendering for the `CLAUDE_TEMPLATE.md`
prompt display that the plain fallback below couldn't do. The bullets
below describe the retired bash/PowerShell behavior for historical
context only:

- If gum was already on PATH, it was used untouched. If not,
  `scripts/ensure-gum.sh`/`.ps1` (now deleted) downloaded the matching
  release binary into a `mktemp -d` for that run only, removed on exit
  (`trap ... EXIT` / `finally`) - nothing was ever installed system-wide.
- Every gum call was guarded by "if $GUM is set"; a failed download
  (offline, unsupported OS/arch) fell back to plain
  `printf`/`Write-Host` output rather than aborting setup.
- Styling was a single foreground color per line, no borders/boxes/bold -
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
services (Obsidian vault, Bifrost instance). Kept
private by default; secrets themselves are never committed (see
`mcp-servers.json` placeholders) so it could be made public later
after a final scan.

## MCP servers are tested by driving a real `claude -p` session

Checking that a binary is on PATH says nothing about whether a
*registered* MCP server actually answers, so `tests/test_mcp_servers.py`
(a `pytest` suite, part of `uv run pytest`, marked `integration`) drives
a real `claude -p --model sonnet` session per server and checks the
result.

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
  backs the browser-use and Lightpanda cases.
- `octocat/Hello-World` - the canonical GitHub test repo; its `README` has
  read `Hello World!` since 2011.
- Context7 asserts on the registry-assigned ID `/colinhacks/zod`, which
  the model cannot plausibly produce without a real lookup.

Cases skip (rather than fail) when a server isn't registered or a
prerequisite is missing, so the suite stays meaningful on a partial setup.
There is no vault case any more (no vault server); if one ever returns,
keep it read-only - a test must never write into someone's real vault.

## Lightpanda behind @playwright/mcp did not work - switched to its native MCP server

`tests/test_mcp_servers.py` (originally `scripts/test-mcp.py`) found the `lightpanda-playwright` server
(`@playwright/mcp` driven over `--cdp-endpoint`) to be broken. Two
separate causes:

1. `--cdp-endpoint ws://localhost:9222` never completes the WebSocket
   handshake, while `ws://127.0.0.1:9222` connects immediately - fixed in
   `mcp-servers.json`. Lightpanda rejects any upgrade request carrying
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

`mcp-servers.json`'s `lightpanda-playwright` entry has been replaced
with `lightpanda` (`command: lightpanda`, `args: ["mcp"]`), and
`tests/test_mcp_servers.py`'s case now drives `evaluate` directly. This does
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
`BU_CDP_WS` embeds a per-launch browser UUID. `tests/test_mcp_servers.py` starts
a headless Chromium on 9223 when nothing is there and injects
`BU_CDP_URL` into the server entry for the test session only.
