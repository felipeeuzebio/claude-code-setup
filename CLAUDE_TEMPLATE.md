Generate or refresh `CLAUDE.md` at the root of the current project using the
template below. This is not Claude Code's generic `/init` output - every
section must reflect what's actually in *this* repo, not filler.

1. Inspect the repo before writing anything: package manifests (`package.json`,
   `pyproject.toml`, `go.mod`, `Cargo.toml`, `Gemfile`, ...), lockfiles, config
   files (linter/formatter/type-checker configs), the top-level directory
   layout, and any existing README/CONTRIBUTING docs. Run the scripts you find
   (`package.json` scripts, `Makefile` targets, etc.) if that's the only way
   to confirm they're the real dev/build/test/lint commands - don't guess.
2. If `CLAUDE.md` already exists, summarize what you'd change (added/removed/
   changed lines, section by section) and wait for confirmation before
   overwriting it. Don't silently clobber hand-written content.
3. Fill in every bracketed placeholder from what you found. If something is
   genuinely undeterminable from the repo (e.g. a deploy target not visible
   in code, or a domain decision only a human would know), leave that one
   placeholder as-is rather than inventing an answer.
4. Keep the whole file under ~150 lines. If a topic needs more than a couple
   lines, put it in `docs/*.md` and link it from the relevant section instead
   of inlining it here - every line in CLAUDE.md competes for attention on
   every turn.

Template:

```markdown
# [Project name]

[One-sentence description of what this project does and who it's for.]

## Stack

- [Language + version]
- [Framework]
- [Database]
- [Key libraries worth naming]
- Deployed on [platform]

## Structure

- `[src/dir1/]` - [what lives here]
- `[src/dir2/]` - [what lives here]
- `[tests/]` - [test layout]
- `[docs/]` - [what's documented and where]

## Commands

- Dev: `[command]`
- Build: `[command]`
- Test: `[command]`
- Lint: `[command]`
- Type check: `[command]`

## Verification

After every change, run in this order and fix before moving on:

1. `[type check command]`
2. `[test command]`
3. `[lint command]`

## Conventions

- [Naming pattern, e.g. how modules/files are named]
- [Where config/constants live]
- [State management or architectural pattern in use]
- For [complex/non-obvious area], see `docs/[guide].md`

## Don't

- [Anti-pattern seen in this codebase] - do [X] instead
- [Anti-pattern seen in this codebase] - do [X] instead
```
