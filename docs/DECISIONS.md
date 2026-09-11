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

- **browser-use** is an agent framework: give it a task in natural language,
  it decides the steps. Self-hosted (see the addendum below) for
  exploratory, task-level browsing.
- **Lightpanda** is a browser *engine* (CDP-compatible, built from scratch in
  Zig, ~11x faster / ~1/16th the memory of headless Chrome). It's wired in as
  the backend for the Playwright MCP via `--cdp-endpoint`, for
  performance-sensitive scripted scraping where you already know the steps.

Use browser-use when you'd otherwise write scraping logic by hand; use the
Lightpanda-backed Playwright MCP when you already have a deterministic
sequence and just want it fast and cheap to run repeatedly.

**Addendum: browser-use switched from hosted to self-hosted.** It
originally pointed at `api.browser-use.com/mcp` (their paid cloud service,
needing `BROWSER_USE_API_KEY`) - the one non-self-hosted piece in an
otherwise self-host-everything setup, and a real inconsistency once
someone actually looked at `.env.example` next to Firecrawl. Switched to
running it locally instead: `uvx browser-use[cli] --mcp` (`uvx` is
Python's on-demand package runner, the same role `npx` plays for the
Node-based servers here - no separate `pip install` step, just `uv` on
PATH). Two things worth knowing before assuming any LLM key works:

- The MCP server's LLM client is hardcoded to `ChatOpenAI`
  (`browser_use/mcp/server.py`) even though the underlying `browser-use`
  library supports Anthropic, Google, Azure, and others - so it only reads
  `OPENAI_API_KEY` (confirmed against `browser_use/config.py`'s env-var
  overrides for the MCP path specifically), not a generic "bring your own
  provider" key. `BROWSER_USE_LLM_MODEL` overrides the default model if
  needed.
- `setup.sh`/`setup.ps1` check for `uvx` the same way they check for
  `docker` - a soft warning, not a blocking requirement - and
  `merge-mcp-config.py` only registers `browser-use` when both `uvx` is on
  PATH and `OPENAI_API_KEY` is set, same "don't write a broken entry"
  rule as everything else here.

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

Lightpanda is Linux/macOS-only (no native Windows build as of this
writing), so `setup.ps1` skips it outright rather than half-installing;
the full stack including Lightpanda needs `setup.sh` under WSL2 on
Windows machines.

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

## Repo: private

The repo stores MCP server topology and setup scripts referencing personal
services (self-hosted Firecrawl, Obsidian vault, Bifrost instance). Kept
private by default; secrets themselves are never committed (see
`mcp/mcp-servers.json` placeholders) so it could be made public later after
a final scan.
