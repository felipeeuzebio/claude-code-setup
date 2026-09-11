# Bifrost MCP gateway

Bifrost (Maxim AI) fronts every MCP server behind one endpoint and doubles as
an LLM gateway. Docs: https://docs.getbifrost.ai

Status as of this setup: running locally via `npx -y @maximhq/bifrost`,
responding on `http://localhost:8080`. It was started in the foreground of a
background shell job, not as a managed service - it will not survive a
reboot. Turn it into a real service (systemd unit, pm2, or the Docker form)
once you're happy with the config.

## 1. Run it

Pick one:

```bash
# npx (no Docker needed)
npx -y @maximhq/bifrost

# or Docker
docker pull maximhq/bifrost
docker run -p 8080:8080 maximhq/bifrost
```

Default port is `8080`. Web UI: http://localhost:8080

By default Bifrost stores its config in SQLite and is edited through the UI.
If you want a file-only, UI-edits-disabled setup instead, create a
`config.json` with `"config_store": {"enabled": false}` next to wherever you
run it, and check the current docs for the full schema before relying on it
— it wasn't fully documented at the time this was written.

## 2. Point Claude Code at it

```bash
claude mcp add --transport http bifrost http://localhost:8080/mcp \
  --header "Authorization: Bearer <your-virtual-key>" \
  --scope user
```

Verify with `/mcp` inside Claude Code.

## 3. Register downstream MCP servers

Do this through the Bifrost web UI (Settings → MCP → Add Server) rather than
hand-editing a config Bifrost doesn't document — for each one, paste in the
command/args/env from `../mcp/mcp-servers.json`, or the HTTP URL for the
remote ones (Context7 if you use its hosted variant).

Add, in this order (cheapest to verify first):

1. **Context7** — no key needed, good smoke test for the gateway.
2. **GitHub** — needs `GITHUB_PERSONAL_ACCESS_TOKEN`.
3. **Codegraph** — local stdio, no key.
4. **Obsidian (librarian-mcp)** — local stdio, reads the vault off disk;
   needs `OBSIDIAN_VAULT_PATH` (no Obsidian process, no REST API plugin).
5. **browser-use** — local stdio via `uvx browser-use[cli] --cli-mcp`, no
   key (Claude drives the browser directly - see `docs/DECISIONS.md`).
6. **Lightpanda-backed Playwright** — needs `lightpanda serve` running first.
7. **Firecrawl** — point at your self-hosted instance once
   `scripts/setup-firecrawl.sh` is up, or use the cloud key.

## 4. Sanity check

`/mcp` in Claude Code should list tools from every server you added, grouped
under the single `bifrost` connection.
