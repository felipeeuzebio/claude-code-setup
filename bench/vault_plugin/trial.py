"""claude-obsidian trial (2026-09-16): would the Claude Code plugin replace
librarian-mcp as the vault tool? Runs plugin skills through `claude -p
--plugin-dir` inside a *copy* of the vault and records calls/bytes/usage the
same way bench/harness.py does. Not wired into harness.run_session because the
plugin needs --plugin-dir and a cwd inside the vault, not --mcp-config.

Setup (all on a copy, never the real vault - adopt/save write to it):
  git clone https://github.com/AgriciDaniel/claude-obsidian  -> PLUGIN
  cp -r "$OBSIDIAN_VAULT_PATH" VAULT
  python3 PLUGIN/scripts/claude-obsidian.py adopt VAULT ...  (plan, then --apply)
  cp -r "VAULT/Indexed Docs/drizzle" VAULT/wiki/sources/     (index covers wiki/ only)
  python3 PLUGIN/scripts/contextual-prefix.py --vault VAULT --all --no-llm
  python3 PLUGIN/scripts/bm25-index.py --vault VAULT build
Run: uv run python bench/vault_plugin/trial.py [q4 q7 save q-saved cross]
Results: results.md next to this file; raw sessions in trial.jsonl (gitignored).
"""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path

S = Path(__file__).parent
# Point these at the scratch copies described above.
VAULT = Path(os.environ.get("TRIAL_VAULT", S / "vault-trial"))
PLUGIN = Path(os.environ.get("TRIAL_PLUGIN", S / "claude-obsidian"))
MODEL = "sonnet"
DENIED = "WebFetch,WebSearch,Task,NotebookEdit"

def parse(stdout):
    calls, tool_bytes, errs, usage, answer, skills = [], 0, 0, {}, "", []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"): continue
        try: ev = json.loads(line)
        except json.JSONDecodeError: continue
        k = ev.get("type")
        if k == "assistant":
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    n = b.get("name", "")
                    if n == "Skill": n += ":" + str(b.get("input", {}).get("skill") or b.get("input", {}).get("command"))
                    if n == "Bash": n += ":" + str(b.get("input", {}).get("command", ""))[:70]
                    calls.append(n)
        elif k == "user":
            for b in ev.get("message", {}).get("content", []) or []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content")
                    t = "".join(x.get("text", "") for x in c if isinstance(x, dict)) if isinstance(c, list) else str(c or "")
                    tool_bytes += len(t.encode()); errs += bool(b.get("is_error"))
        elif k == "result":
            answer, usage = str(ev.get("result") or ""), ev.get("usage") or {}
    return calls, tool_bytes, errs, usage, answer

def run(name, prompt, cwd, plugin=True, env_extra=None, allowed="Skill,Bash,Read,Write,Edit,Glob,Grep"):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "mcp.json"; cfg.write_text('{"mcpServers":{}}')
        cmd = ["claude", "-p", prompt, "--model", MODEL, "--output-format", "stream-json", "--verbose",
               "--strict-mcp-config", "--mcp-config", str(cfg),
               "--allowedTools", allowed, "--disallowedTools", DENIED]
        if plugin: cmd += ["--plugin-dir", str(PLUGIN)]
        env = dict(os.environ, **(env_extra or {}))
        t0 = time.time()
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=cwd, stdin=subprocess.DEVNULL, env=env)
        wall = time.time() - t0
    calls, tb, errs, usage, answer = parse(p.stdout)
    rec = dict(name=name, calls=calls, n_calls=len(calls), tool_bytes=tb, errors=errs, wall_s=round(wall, 1),
               out_tok=usage.get("output_tokens"), cache_read=usage.get("cache_read_input_tokens"),
               cache_create=usage.get("cache_creation_input_tokens"), answer=answer[:1200], stderr=p.stderr[-800:])
    print(f"{name:14} calls={len(calls):2} bytes={tb:6} err={errs} wall={wall:5.1f}s out={rec['out_tok']} cached={rec['cache_read']}")
    for c in calls: print("    ", c)
    print("   answer:", answer[:600].replace("\n", " | "))
    (S / "trial.jsonl").open("a").write(json.dumps(rec) + "\n")
    return rec

if __name__ == "__main__":
    which = sys.argv[1:] or ["q4", "q7", "save", "q-saved", "cross"]
    if "q4" in which:
        run("q4", "Use the wiki-query skill to answer from the vault: In Drizzle ORM, how do I run multiple writes inside a transaction, and how do I roll it back? Cite the vault note you used.", VAULT)
    if "q7" in which:
        run("q7", "Use the wiki-query skill to answer from the vault: In Drizzle ORM, how do I do an upsert (insert, or update on conflict)? Cite the vault note you used.", VAULT)
    if "save" in which:
        run("save", "Use the save skill to record this insight in the vault: 'Claude Code's built-in WebFetch returns a prompt-driven summary of a page; asked for exact text it reproduces it verbatim (measured 2026-09-16, bench/web_tools/verbatim.py, 12/12 correct, 223-546 bytes per answer). Escalate to Lightpanda only for JS-rendered pages.' Source: local benchmark, claude-code-setup repo.", VAULT)
    if "q-saved" in which:
        run("q-saved", "Use the wiki-query skill: what does the vault say about WebFetch and when to escalate to Lightpanda?", VAULT)
    if "cross" in which:
        run("cross", "Use the wiki-query skill: what does the vault say about WebFetch and when to escalate to Lightpanda?",
            "/home/felipe/my_projects/standalone/claude_projects/claude-code-setup", env_extra={"CLAUDE_OBSIDIAN_VAULT": str(VAULT)})
