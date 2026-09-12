# Setup decisions

Recorded 2026-09-11, so future-me remembers *why*, not just *what*.

## Bifrost as the MCP gateway

Bifrost (Maxim AI) was chosen over running each MCP server directly against
Claude Code because it doubles as an LLM gateway (cost/observability across
model calls) and an MCP aggregator (one `/mcp` endpoint fronting every
downstream tool server), in a single self-hostable Go binary. No other
open-source option combines both roles.

Caveat: Bifrost's own docs don't fully spell out the config-file schema for
registering downstream MCP servers — that's done through its web UI
(`http://localhost:8080`) or management API, not by hand-editing JSON we
control. Treat `bifrost/SETUP.md` as the source of truth and re-check
`docs.getbifrost.ai` if the UI has moved things around.

## Firecrawl: self-hosted via Docker, not cloud

Chose to enable Docker Desktop's WSL integration (rather than installing
Docker Engine natively in the WSL2 distro, or just using Firecrawl Cloud)
because Docker Desktop was already the assumed setup. `docker --version`
was not found in-distro at the start of this session but was present by
the time `scripts/setup-firecrawl.sh` ran — confirming WSL integration was
enabled correctly.

Two real issues came up bringing the stack up for the first time, both
fixed and captured in `scripts/setup-firecrawl.sh` / `firecrawl/.env.example`:

- **RabbitMQ `EACCES` on `.erlang.cookie`** on the very first `up` - a
  known Docker-Desktop-on-WSL2 anonymous-volume permission quirk. Fixed by
  `docker compose down -v && docker compose up -d` once; if it recurs,
  it's the same class of issue, not a config problem.
- **`NUQ_BACKEND=postgres` is not a valid value** - the API only accepts
  `pg` or `fdb`. Set to `pg` since this compose file brings up
  `nuq-postgres`.

Verified working end-to-end with a live `POST /v1/scrape` against
`https://example.com` through the running container, not just a port
check.

Both of these are WSL2/Docker-Desktop-specific quirks, not something
`scripts/setup-firecrawl.sh` itself requires - on native Linux with Docker
Engine installed directly (no Docker Desktop, no WSL layer in between),
`docker compose up -d` just works with no anonymous-volume permission
class of issue to hit in the first place. `setup.sh`'s docker check
(`command -v docker && docker info`) and the Firecrawl bring-up script are
plain `docker compose` calls with no WSL-specific logic - the only place
that branches on WSL vs. native Linux is the error message printed when
`docker` isn't found at all, so it points at the right fix either way.

## browser-use + Lightpanda: both, not either/or

These aren't competing choices — they sit at different layers:

- **browser-use** gives Claude Code low-level browser control
  (`browser_exec`/`browser_screenshot`, backed by browser-use's Chromium
  "browser harness") for exploratory browsing where you don't already know
  the exact sequence of steps. Self-hosted, no API key - see the addendum
  below for how that landed here.
- **Lightpanda** is a browser *engine* (CDP-compatible, built from scratch in
  Zig, ~11x faster / ~1/16th the memory of headless Chrome). It's wired in as
  the backend for the Playwright MCP via `--cdp-endpoint`, for
  performance-sensitive scripted scraping where you already know the steps.

Use browser-use when you'd otherwise write scraping logic by hand; use the
Lightpanda-backed Playwright MCP when you already have a deterministic
sequence and just want it fast and cheap to run repeatedly.

**Addendum: browser-use's MCP *mode*, not just its hosting, changed.**
Went through three iterations getting this right:

1. Started pointing at `api.browser-use.com/mcp`, their paid cloud service
   (`BROWSER_USE_API_KEY`) - the one non-self-hosted piece in an otherwise
   self-host-everything setup, a real inconsistency once someone actually
   looked at `.env.example` next to Firecrawl.
2. Switched to running it locally instead: `uvx browser-use[cli] --mcp`
   (`uvx` is Python's on-demand package runner, the same role `npx` plays
   for the Node-based servers here). But `--mcp` runs browser-use's own
   internal autonomous agent, and its LLM client is hardcoded to
   `ChatOpenAI` (`browser_use/mcp/server.py`) even though the underlying
   `browser-use` *library* supports many providers - so it only reads
   `OPENAI_API_KEY`, not a generic "bring your own provider" key.
   `LLMEntry` in `browser_use/config.py` doesn't even have a `base_url`
   field, so pointing it at an OpenAI-compatible endpoint (DeepSeek,
   OpenRouter's OpenAI-compatible mode, etc. - see
   [docs.browser-use.com/open-source/supported-models](https://docs.browser-use.com/open-source/supported-models))
   isn't actually wired up in the packaged MCP server, despite the docs
   describing broad provider support at the library level. The only other
   provider genuinely wired into `--mcp` is AWS Bedrock
   (`MODEL_PROVIDER=bedrock`, using your AWS credentials) - a real option
   if you already have Bedrock model access, but not a fit here.
3. Landed on `uvx browser-use[cli] --cli-mcp` instead - a completely
   different mode (`browser_use/mcp/cli_mcp.py`). It doesn't run an
   internal agent at all: it exposes `browser_exec` (run Python against a
   persistent browser session - `new_tab`, `goto_url`, `click_at_xy`,
   `js`, `cdp`, etc.) and `browser_screenshot`, and Claude Code itself
   decides what to do with them. No LLM key of any kind, because Claude is
   already the one deciding - the exact role `--mcp`'s internal agent was
   filling.

`setup.sh`/`setup.ps1` check for `uvx` the same way they check for
`docker` - a soft warning, not a blocking requirement - and
`merge-mcp-config.py` registers `browser-use` whenever `uvx` is on PATH,
same "don't write a broken entry" rule as everything else here, just with
nothing left to gate on now that no key is needed.

Two things found by actually running this, not just reading the source:

- **`uvx browser-use[cli]` needs `--python 3.12` pinned explicitly.**
  browser-use requires Python >=3.11, but on this box plain `uvx
  browser-use[cli]` resolved against a stray already-managed Python 3.10
  install and failed dependency resolution outright, even though a
  perfectly good Python 3.14 was the actual system default - `uvx` doesn't
  reliably pick a satisfying interpreter on its own if an older managed
  one is already sitting around. Pinning `--python 3.12` in
  `mcp/mcp-servers.json`'s args fixes it unconditionally (`uv` downloads
  3.12 on demand if it isn't already installed).
- **Chromium install is not something setup.sh/setup.ps1 run for you.**
  `uvx browser-use[cli] install` (needed once, before first real use)
  runs `playwright install chromium --with-deps` on Linux, and
  `--with-deps` shells out to `sudo apt-get install` for system libraries
  - which hung silently the first time because it was wrapped in a `spin`
  spinner that hides command output, swallowing what should have been an
  interactive sudo password prompt. Pulled it out of the automated steps
  entirely; both scripts now just print the exact command to run once in
  the final summary, the same "tell them what's left" treatment already
  used for the Bifrost virtual key. (Windows doesn't hit the sudo case -
  Playwright's `--with-deps` branch is Linux-only - but the instruction is
  kept identical across both scripts for consistency.)

## Codegraph over Graphify

Both are codebase-knowledge-graph MCP servers with heavy feature overlap
(symbol graphs, impact analysis, token-budgeted context). Codegraph was
kept because:

- It was already installed locally (`codegraph` CLI, v1.5.0) — zero extra
  install cost.
- It has a broader tool surface (9 MCP tools: search, context, callers/
  callees, impact, explore, node, files, status) versus Graphify's
  graph-analysis-only focus.
- Running both would mean two overlapping graph indexes to keep in sync
  for no added capability — pure maintenance cost.

Ripgrep alone was ruled out as *sufficient* (not as a tool to drop) because
it can't answer structural questions — "who calls this", "what breaks if I
change this" — that Codegraph answers directly from a persisted graph
instead of re-deriving them from text search every time.

## Obsidian: librarian-mcp instead of mcp-obsidian

Swapped after checking [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)
(53.9k stars, the largest curated Claude Code resource list) which surfaced
several Obsidian options under its "Obsidian" section. Went with
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
- Ships a Linux x86_64 release binary + installer script, so it works
  fine on this WSL2 box without a Homebrew dependency.

Also worth a look but not adopted here: `agentcairn`, `claude-bedrock`,
and `claude-obsidian` from the same list - all take a more opinionated
"second brain" / Zettelkasten angle rather than a plain MCP server, which
is more setup than this pass needed.

**Obsidian running on Windows while the vault is read from elsewhere:**
librarian-mcp ships real prebuilt binaries for all three OSes, including
`librarian-mcp-x86_64-pc-windows-msvc.zip` (confirmed via `gh api
repos/ngmeyer/librarian-mcp/releases/latest`) - it isn't Linux/macOS-only.
Since it reads the vault folder straight off disk rather than talking to
the Obsidian app, the only thing that matters is which filesystem
`OBSIDIAN_VAULT_PATH` points at relative to where librarian-mcp itself
runs:

- **`setup.ps1` (native Windows)**: use a normal Windows path, e.g.
  `C:\Users\you\Documents\MyVault`. Obsidian and librarian-mcp are on the
  same filesystem - no translation needed.
- **`setup.sh` under WSL2, vault on the Windows side**: WSL2 mounts Windows
  drives under `/mnt/c/...`, so point `OBSIDIAN_VAULT_PATH` at e.g.
  `/mnt/c/Users/you/Documents/MyVault` instead of the Windows-style path.
  It works, but cross-boundary file access through the 9p protocol is
  noticeably slower than a native mount - fine for occasional reads/writes,
  worth knowing about if you're running librarian-mcp's trigram search or
  graph analytics over a large vault repeatedly.

Either way, Obsidian.app itself doesn't need to be running at all - only
the vault folder needs to exist wherever the path points.

## setup.sh/setup.ps1: skip rather than write broken entries

Both scripts (and the `scripts/merge-mcp-config.py` they share) only add
an MCP server to `~/.claude.json` once its required secret/path is
present - a `github` entry with a placeholder token would fail on first
use, and a silently-broken MCP server is worse than one that's just not
there yet. Missing pieces are listed at the end of the run instead, so
re-running after adding one line to `.env` is the whole fix.

**Addendum: "present" for `OBSIDIAN_VAULT_PATH` now means a real
directory, not just a non-empty string.** The original check was
`bool(vault_path)` - a typo'd path, or a Windows-style `C:\...` path
handed to the WSL2/Linux `librarian-mcp` binary (which needs
`/mnt/c/...` instead - see the Obsidian section above), would pass that
check, get written into `~/.claude.json`, and only fail later at Claude
Code runtime as an opaque MCP connection error. `build_plan()` in
`scripts/merge-mcp-config.py` now checks `Path(vault_path).is_dir()`,
and `setup.sh`/`setup.ps1` run the same existence check inline so the
warning ("OBSIDIAN_VAULT_PATH is not an existing directory: ...") shows
up during the run itself, not just in the merge step's skip summary.
`build_plan()`'s return type also grew a per-server skip reason string
(previously the merge script's final printout just said "missing
secret/dependency" for every skip, which didn't distinguish "not set"
from "set but invalid").

Lightpanda is Linux/macOS-only (no native Windows build as of this
writing), so `setup.ps1` skips it outright rather than half-installing;
the full stack including Lightpanda needs `setup.sh` under WSL2 on
Windows machines.

**Addendum: `setup.sh`'s own `.env` loader was the thing corrupting
paths, found via a real bug report.** It used to `source .env` directly
(with `set -a`/`set +a` around it) - but `source` runs `.env` as actual
bash, not a plain key/value reader. An unquoted value containing a space,
like a real-world Windows-style `OBSIDIAN_VAULT_PATH=C:\Users\you\Documents\My Vault`,
gets word-split: bash treats `Vault` as a second word after the
assignment and tries to run it as a command ("Vault: command not
found"), and because that's the `VAR=value command` form, the assignment
doesn't even persist to the rest of the script - so the variable ends up
unset, not just malformed. Unquoted backslashes are also interpreted as
shell escapes and silently stripped. `setup.sh` now reads `.env`
line-by-line with plain string ops (`${line%%=*}` / `${line#*=}`) and
`export`s each key directly, never evaluating the value as shell code -
spaces and backslashes survive intact with no quoting required (quoted
values still work too; surrounding quotes are stripped). `setup.ps1`
never had this bug - `Get-Content`/`.Split('=')` there is plain text
splitting, not code execution, so it never interpreted backslashes or
word-split on spaces to begin with.

## CLAUDE.md init: an interactive setup-time ask, not an installed command

First pass at this made `/init-claude-md` a slash command installed into
`~/.claude/commands/`. Reworked into an interactive step inside
setup.sh/setup.ps1 instead, because the actual want was narrower: ask once,
at setup time, whether to generate this repo's `CLAUDE.md` now - and if the
answer is no (or the run is non-interactive), just print the prompt so it
can be pasted into any Claude Code session whenever it's wanted, here or in
another project. That doesn't need a permanently-installed command:

- `claude-md/init-prompt.md` holds the prompt text (instructions + the
  `GENERIC_TEMPLATE.md` structure) with no slash-command frontmatter - it's
  just a prompt, read by the setup scripts and cat-able by a human.
- If `CLAUDE.md` already exists in the repo, the step is skipped outright -
  it never overwrites hand-written project knowledge a repo-scan wouldn't
  rediscover. The "yes" path also tells the model to summarize changes and
  wait for confirmation if the file somehow is present, as a second guard.
- A non-interactive run (no TTY on stdin) never blocks on a prompt - it
  just prints the copy-paste block, same as answering no.
- Saying yes runs `claude -p "$(cat claude-md/init-prompt.md)"` right there,
  since setup.sh/setup.ps1 already `cd` to the repo root before this step.

## gum styling: temp-download, never a system install

setup.sh/setup.ps1 style their output with
[gum](https://github.com/charmbracelet/gum) (styled headers, spinners on
slow installs, `gum confirm` for the CLAUDE.md prompt, `gum format` to
render `init-prompt.md` as markdown instead of a raw text dump). If gum is
already on PATH, that's what gets used - untouched. If not, `scripts/
ensure-gum.sh` (bash) / `scripts/ensure-gum.ps1` (PowerShell) download the
matching release binary into a `mktemp -d` directory for that run only,
and the caller removes it on exit (`trap ... EXIT` in bash, `finally` in
PowerShell). Nothing is ever written to a system bin directory or added to
PATH permanently - re-running setup with no gum installed downloads it
again rather than remembering it, which is fine since gum itself is a
single small binary.

gum is treated as strictly cosmetic: every call is guarded by "if $GUM is
set", and if the download fails (offline, or an OS/arch gum doesn't ship
for) the scripts fall back to the plain `printf`/`Write-Host` output they
had before gum was added, rather than aborting setup over a styling
dependency.

Verified `setup.ps1`'s gum integration without a Windows machine by:
parsing all four `.ps1` files with PowerShell's own
`[System.Management.Automation.Language.Parser]` (via a temporary Linux
build of PowerShell, deleted after), dot-sourcing `ensure-gum.ps1` for
real to confirm it downloads and extracts the actual Windows `gum.exe`
release asset correctly, and running the full `setup.ps1` end-to-end
against this machine's real node/docker/codegraph/librarian-mcp/git with a
throwaway shell-script stand-in for `gum` on PATH (since a Windows PE
binary can't execute on Linux) to exercise the control flow itself.

## gum bootstrap is silent, and Ctrl+C actually quits setup

Two follow-ups after the gum pass above landed:

- Dropped the "Checking for gum..." / "Downloaded a temporary gum..." /
  "Using your existing gum install." lines. They were only ever about the
  bootstrap mechanics, not the setup itself - useful while building this,
  not for someone just running it.
- Ctrl+C during a `gum confirm` or `gum spin` did *not* stop the script.
  gum's TUI puts the terminal in raw mode, so Ctrl+C there is a keystroke
  gum itself interprets (confirmed empirically: exit code 130, distinct
  from 0=yes/1=no for confirm, and from any other command failure for
  spin) - it never becomes an actual SIGINT delivered to this shell. Left
  unhandled, the script would treat a Ctrl+C as "answered no" or "that one
  install failed" and barrel on into the next step, which is exactly what
  "I should be able to quit the setup" was flagging.

Fix: every `gum confirm`/`gum spin` call now checks for exit code 130
specifically and calls `quit_setup`/`Stop-Setup`, which prints "Setup
cancelled." and exits 130 itself - triggering the same EXIT trap /
`finally` block that cleans up a temp-downloaded gum, so quitting mid-setup
doesn't leave anything behind. Verified both the spin and confirm cancel
paths on both setup.sh and setup.ps1 (the latter via the same temporary
Linux PowerShell build used to verify the gum work itself), using a
throwaway stand-in `gum` script that can simulate returning 130 on demand
since a real interactive Ctrl+C can't be scripted here. Plain-fallback
mode (no gum) needed no change - a real terminal `read`/`Read-Host` with
no raw-mode TUI in front of it already receives an actual SIGINT/Ctrl+C
and stops the script by default.

## Gum styling pared back to plain foreground colors, and a spinner-glyph fix

Two more adjustments after using this for a while:

- **Dropped every gum decoration except a single foreground color per
  line**: `--bold` on step headers, the `--margin` gum was using to add
  blank lines (replaced with a plain `echo`/`Write-Host ""` before the
  styled line instead), and - the biggest one - the `--border rounded
  --padding "1 2"` box around the final summary, which is now just
  `gum style --foreground 212` over the same text. None of that added
  information; it just made the output louder than a setup script needs
  to be.
- **`gum spin` now passes `--spinner line`** instead of leaving gum on its
  default `dot` spinner. `dot`'s animation frames are single Unicode
  Braille Pattern characters (confirmed against bubbles' spinner
  definitions - gum vendors that package); a terminal or font without full
  Braille Pattern coverage (common on stock Windows Terminal / WSL2 setups)
  renders those as mangled boxes, which is what showed up as "weird
  characters" right after the `...` in a spinner title like "Bringing up
  self-hosted Firecrawl...". `line` animates through plain ASCII
  (`| / - \`) instead - no font dependency, and it reads as more minimal
  too.

Re-ran `setup.sh` end-to-end afterward (piping `n` to the CLAUDE.md
prompt) to confirm the trimmed styling still renders correctly and nothing
regressed in the confirm/spin/summary flow.

## Codegraph install output hidden, and a post-install index/sync prompt added

`codegraph install --target claude --location global -y` ran unwrapped in
both scripts, so its own fancy status box (its own terminal UI library,
not gum) printed straight to the terminal every run - including, in
practice, a couple of duplicated "Claude Code: Unchanged ~/.claude/..."
lines, which is codegraph's own output, not something under this repo's
control. Wrapped it in the existing `spin`/`Invoke-Spin` helper (same
treatment already given to codegraph's install-from-scratch curl step,
Firecrawl bring-up, etc.) so it's hidden unless it fails, replaced by our
own one-line "registered" confirmation.

Also replaced codegraph's printed "Next: index a project" hint - which
just prints generic instructions regardless of this repo's state - with
an actual interactive step: if `.codegraph/` doesn't exist yet, ask (via
the same gum-confirm/plain-read pattern as the CLAUDE.md step) whether to
run `codegraph init` now; if it already exists, offer `codegraph sync`
instead. A non-interactive terminal gets the command printed instead of
being asked (same convention as the CLAUDE.md step). Extracted a shared
`confirm()` (bash) helper for this since `setup.sh`'s CLAUDE.md step had
been inlining the identical gum-confirm/read-fallback logic; `setup.ps1`
already had this as `Confirm-Gum`, reused as-is.

Verified live: a full `setup.sh` run against a scratch copy of the repo
(never the real repo, since `codegraph init` writes `.codegraph/` into
whatever directory it's run from) confirmed no duplicated/box output
before the "registered" line, correct switching between the `init` and
`sync` prompts based on whether `.codegraph/` already existed, and that
declining either one leaves the directory untouched.

## Commit message convention enforced via a commit-msg hook, not pre-commit

Every commit up to this point had a wordy, non-conventional message. Fixed
going forward with a hook requiring `type: concise summary` (Conventional
Commits, types restricted to the set already declared in this machine's
global git-workflow rules: feat/fix/refactor/docs/test/chore/perf/ci,
<=72 chars, no scope required but `type(scope):` is accepted) plus, if a
body is present, every line must be a `- ` bullet or a trailer
(`Co-Authored-By: ...` and similar `Token: value` lines are exempt from
the bullet rule specifically so attribution trailers still work).

This had to be a **commit-msg** hook, not pre-commit as originally asked
for - pre-commit runs before the commit message is written and is never
given it as an argument, so it structurally cannot validate message
content. commit-msg receives the message's temp file path as `$1` and
can reject the commit by exiting non-zero.

The script itself lives at `githooks/commit-msg`, tracked in the repo,
rather than dropped straight into `.git/hooks/` - hooks placed there
aren't committed or cloned with the repo, so every clone would silently
have no enforcement at all. `git config core.hooksPath githooks` points
git at the tracked directory instead; `setup.sh`/`setup.ps1` run that
config command as their first step so it's wired up automatically on
setup, not just on the machine that authored it.

Verified live: fed the hook nine hand-built cases (valid message, valid
with no body, valid with a scope, invalid type, subject over the length
limit, missing blank line before the body, a prose body line, a
trailer-only body, and an empty message) - all matched their expected
accept/reject outcome. Then, separately, staged this hook's own file and
ran a real `git commit` with a deliberately non-conventional message
against it live (not just the script standalone) to confirm git itself
actually invokes and enforces it once `core.hooksPath` is set - it was
rejected as expected.

**Existing history was rewritten to match**, since all 16 prior commits
predated this hook and used the old verbose/non-conventional style -
see the commit that follows this one for how.

## Repo: private

The repo stores MCP server topology and setup scripts referencing personal
services (self-hosted Firecrawl, Obsidian vault, Bifrost instance). Kept
private by default; secrets themselves are never committed (see
`mcp/mcp-servers.json` placeholders) so it could be made public later after
a final scan.

## MCP servers are tested by driving a real `claude -p` session

`scripts/verify-env.sh` only proves binaries are on PATH. That says nothing
about whether a *registered* MCP server actually answers, so
`scripts/test-mcp.py` drives a real `claude -p --model sonnet` session per
server and checks the result.

The hard part is that most of these prompts can be answered *without* the
server under test - the model already knows what octocat/Hello-World's
README says, and can reach a URL with WebFetch. A naive harness would go
green against a completely dead server. So every case is validated in three
independent layers:

1. **connected** - the server's tools appear in the session's `init` event
2. **invoked** - the expected tool shows up as a real `tool_use` in the
   transcript
3. **correct** - the final answer matches an expected pattern

and each case runs with `--strict-mcp-config` (only the server under test),
a tool allowlist, and an explicit denylist of
WebFetch/WebSearch/Bash/Read/Glob/Grep. This was verified by pointing the
GitHub case at a nonexistent binary: it fails at layer 1 rather than
passing from the model's own knowledge.

Test pages were chosen to be stable and to have a *discriminating* answer:

- `example.com` - IANA-maintained, reserved by RFC 2606. Assertions use the
  `Example Domain` heading, not the body copy, which has since been
  reworded from the familiar "illustrative examples in documents".
- `quotes.toscrape.com/js/` - Zyte's scraping sandbox, published for exactly
  this purpose. Its quote list is built from a `var data = [...]` array by
  JavaScript, so a JS-executing browser sees 10 `.quote` elements and a
  plain HTTP fetch sees 0. That single number separates a real headless
  browser from a bare fetch, which is why it backs the Firecrawl, browser-use
  and Lightpanda cases.
- `octocat/Hello-World` - the canonical GitHub test repo; its `README` has
  read `Hello World!` since 2011.
- Context7 asserts on the registry-assigned ID `/colinhacks/zod`, which the
  model cannot plausibly produce without a real lookup.

Cases skip (rather than fail) when a server isn't registered or a
prerequisite is missing, so the suite stays meaningful on a partial setup.
The Obsidian case is deliberately read-only (`library_stats`) - a test must
never write into someone's real vault.

## Lightpanda behind @playwright/mcp does not work

`scripts/test-mcp.py` found the `lightpanda-playwright` server to be broken.
Two separate causes, both confirmed directly against the CDP endpoint:

1. `--cdp-endpoint ws://localhost:9222` never completes the WebSocket
   handshake, while `ws://127.0.0.1:9222` connects immediately. Fixed in
   `mcp/mcp-servers.json`. Lightpanda also rejects any upgrade request
   carrying an `Origin` header with a 403, which is the likely mechanism.
2. With the connection fixed, navigation still times out. Playwright waits
   for a `Page.lifecycleEvent`/`frameStoppedLoading` after `Page.navigate`;
   Lightpanda 1.0.0-nightly answers the `Page.navigate` command but emits no
   such event, so every `goto` hangs until timeout regardless of
   `waitUntil`. Reproduced with playwright-core 1.59, 1.62 and 1.63, and by
   speaking raw CDP over a hand-rolled WebSocket client.

Lightpanda itself is fine - `lightpanda fetch --dump` renders pages, and its
own `lightpanda mcp` stdio server navigates and evaluates correctly
(`evaluate` with `{url, script}` on the JS quotes page returns `10`). That
server needs no separate `serve` process, no port, and no `@playwright/mcp`
dependency, and exposes a richer surface (`goto`, `markdown`, `evaluate`,
`extract`, form/DOM tools, sessions).

Switching to it is the obvious fix, but it changes the tool surface agents
see, so it is left as a decision rather than applied here. The suite keeps
failing on this server on purpose: it is genuinely broken, and hiding that
behind an expected-failure marker would defeat the point of the suite.

## browser-use needs a browser already running

`browser-use --cli-mcp` attaches to a running Chromium-family browser; it
never launches one. On a headless box nothing is running, so every call
fails with `chrome-not-running`, even though `setup.sh` installs Chromium.

Its discovery probes only ports 9222 and 9223, and 9222 is where Lightpanda
listens - which browser-use correctly refuses, since Lightpanda is not a
Chromium-family browser. The reliable fix is the documented `BU_CDP_URL`
override: `http://127.0.0.1:9223` is stable, whereas `BU_CDP_WS` embeds a
per-launch browser UUID. `scripts/test-mcp.py` starts a headless Chromium on
9223 when nothing is there and injects `BU_CDP_URL` into the server entry
for the test session only.
