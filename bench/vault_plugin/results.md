# Vault tool trial: claude-obsidian plugin vs librarian-mcp (2026-09-16)

Question: should [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian)
(Claude Code plugin, v2.2.0, 15k stars) replace librarian-mcp (MCP server, 29
stars, last push 2026-06) as the Obsidian vault tool?

Everything ran on a **copy** of the vault; the real one was not touched.
Harness: `trial.py` (plugin sessions via `claude -p --plugin-dir`, model
`sonnet`, MCP disabled, WebFetch/WebSearch denied). librarian-mcp numbers are
the vault arm of `bench/docs_retrieval` on the same Drizzle pages.

## What was checked

| Check | Result |
|---|---|
| `adopt` an existing vault (ext4 copy) | Additive, transactional, 11 files (`wiki/`, `inbox/`, `.raw/`, config). Existing notes untouched. |
| `adopt` a copy on `/mnt/c` (where the real vault lives) | **Fails.** All 11 writes applied, then `RESULT_DRIFT`: it enforces mode `0600`, drvfs reports `0777` (no `metadata` mount option), rolled back cleanly. Every transactional write (`save`, ingest, `mode set`) would fail the same way. Their WSL guide says "NTFS is fine" - the drvfs case is undocumented. |
| Index build (191 pages -> 905 chunks) | 14 s on ext4; **6 min 23 s on `/mnt/c`** (small-file I/O over 9p). Retrieve: 0.6 s vs 1.7 s. |
| Retrieval quality (BM25 `retrieve.py`, top 3, 8 Drizzle bench questions) | Expected page in top 3 for **8/8** (rank 1 for joins/upsert, rank 2 for migrations/unique/serial, rank 3 for select/transactions/rqb). Real snippets on multi-word queries - librarian-mcp returned none. |
| What the index covers | **`wiki/**` only.** `Indexed Docs/` and any note outside `wiki/` are invisible to `wiki-query` until moved or ingested there. `adopt` doesn't move anything. |
| Hooks (SessionStart, Stop; python3) | 0.3-0.8 s each, fire in every session of every project once installed at user scope. |
| Cross-project use | Works with `CLAUDE_OBSIDIAN_VAULT` set (session started in this repo, vault elsewhere). |

## Sessions

All answers were correct (Q4/Q7 pass the bench regexes; `save` produced a
well-formed concept note plus ledgers, index, log and hot-cache updates in one
transaction; both queries of the saved note cited it with its provenance).

| Session | Tool calls | Tool output | Wall | Output tokens | Cached input tokens | Errors |
|---|---|---|---|---|---|---|
| Q4 transactions (`wiki-query`) | 11 | 13.3 KB | 264 s | 3,293 | 710k | 0 |
| Q7 upsert (`wiki-query`) | 9 | 20.8 KB | 157 s | 2,163 | 577k | 0 |
| `save` one insight | **52** | 70.7 KB | **439 s** | **20,530** | **4,626k** | 3 |
| query the saved note (`wiki-query`) | 11 | 6.5 KB | 189 s | 3,264 | 514k | 0 |
| same, from another project (env var) | 5 | 7.2 KB | 80 s | 1,892 | 343k | 0 |
| *librarian-mcp, Q4/Q7 (docs bench median)* | *2* | *13.8 KB* | *14 s* | - | - | *0* |
| *Context7, same questions (docs bench median)* | *2* | *5.6 KB* | *20 s* | - | - | *0* |

Why so many calls - visible in every trace:

1. `SKILL.md` says "resolve the product root from this skill's own location"
   with a literal `/absolute/path/to/installed/claude-obsidian` placeholder,
   so 4 of 5 sessions began with `find / -maxdepth 6 -iname claude-obsidian`.
2. The skills are procedures for Claude to drive a Python CLI by hand
   (`contracts --verify`, `retrieve.py`, ledger JSON, `transaction apply`),
   each step a Bash turn. In Q7 it abandoned the pipeline and `grep -rli`'d
   the wiki instead.
3. `save` had to learn the ledger/transaction schema, and did so by reading
   the plugin's source (`grep "^def \|^class"`, `sed -n '3440,3465p'` on
   `transaction.py`) - ~20 of its 52 calls.
4. `save` does not refresh the BM25 index and `wiki-query` must not rebuild
   it, so the query of the saved note got 0 hits and fell back to reading
   `hot.md`/`index.md` - fine for a tiny vault, not for a real one.

Turn count is what sets the token bill (each turn re-reads ~100k cached
tokens - same finding as `bench/web_tools`), so one `wiki-query` costs about
5x a librarian-mcp lookup and one `save` about 30x.

## Verdict

**Not now.** Two blockers and one cost problem, in that order:

- **It cannot write to the vault where the vault is.** Fixing that means either
  `[automount] options = "metadata"` in `/etc/wsl.conf` (system-wide change,
  WSL restart, and still 25x slower indexing over 9p) or moving the vault into
  the WSL filesystem (changes how Obsidian on Windows opens it).
- **It replaces the vault layout, not just the tool.** Everything you want
  searchable must live under `wiki/`, in its page shapes, with its ledgers.
  That is the "second brain" it sells; it is not a drop-in for "search and
  read my notes".
- **5-30x the tokens and 10-30x the wall time of librarian-mcp per operation**,
  for the same correctness, because the plugin is instructions for Claude to
  operate a CLI rather than a tool Claude calls once.

What it does better, for the record: retrieval snippets, transactional writes
with rollback, provenance ledgers, skills that trigger by description (no
`WEB_TOOLS`-style routing block needed), and it is maintained.

Revisit when *both* hold: the vault is on a filesystem where its writes
succeed, and a release resolves the product root itself (or ships an MCP/CLI
surface Claude can call in one turn). Either alone doesn't change the answer.
