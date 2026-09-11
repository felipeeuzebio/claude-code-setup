#!/usr/bin/env node
// Merges the MCP servers this repo manages into ~/.claude.json, skipping any
// server whose required secret/path isn't available rather than writing a
// broken entry. Shared by setup.sh and setup.ps1 so the merge logic - and
// its bugs - only exist in one place.
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const sourcePath = path.join(repoRoot, "mcp", "mcp-servers.json");
const targetPath = path.join(os.homedir(), ".claude.json");

const env = process.env;
const githubToken = env.GITHUB_TOKEN || env.GITHUB_PERSONAL_ACCESS_TOKEN || "";
const browserUseKey = env.BROWSER_USE_API_KEY || "";
const vaultPath = env.OBSIDIAN_VAULT_PATH || "";
const firecrawlUrl = env.FIRECRAWL_API_URL || "http://localhost:3002";
const skipFirecrawl = /^(1|true)$/i.test(env.SKIP_FIRECRAWL || "");
const hasLightpanda = /^(1|true)$/i.test(env.HAS_LIGHTPANDA || "");

const source = JSON.parse(fs.readFileSync(sourcePath, "utf8")).mcpServers;

// name -> whether it's ready to register, and how to fill it in
const plan = {
  context7: { ready: true, fill: (s) => s },
  github: {
    ready: Boolean(githubToken),
    fill: (s) => ({ ...s, env: { GITHUB_PERSONAL_ACCESS_TOKEN: githubToken } }),
  },
  firecrawl: {
    ready: !skipFirecrawl,
    fill: (s) => ({ ...s, env: { ...s.env, FIRECRAWL_API_URL: firecrawlUrl } }),
  },
  obsidian: {
    ready: Boolean(vaultPath),
    fill: (s) => ({ ...s, args: [vaultPath] }),
  },
  "browser-use": {
    ready: Boolean(browserUseKey),
    fill: (s) => ({ ...s, headers: { "x-browser-use-api-key": browserUseKey } }),
  },
  "lightpanda-playwright": {
    ready: hasLightpanda,
    fill: (s) => s,
  },
};

const registered = [];
const skipped = [];
const toWrite = {};

for (const [name, server] of Object.entries(source)) {
  const rule = plan[name];
  if (!rule) continue; // codegraph is registered by its own installer, not here
  if (rule.ready) {
    toWrite[name] = rule.fill(server);
    registered.push(name);
  } else {
    skipped.push(name);
  }
}

let target = { mcpServers: {} };
if (fs.existsSync(targetPath)) {
  target = JSON.parse(fs.readFileSync(targetPath, "utf8"));
  target.mcpServers = target.mcpServers || {};
  const backupPath = `${targetPath}.bak-${Date.now()}`;
  fs.copyFileSync(targetPath, backupPath);
  console.log(`Backed up existing config to ${backupPath}`);
}

target.mcpServers = { ...target.mcpServers, ...toWrite };
fs.writeFileSync(targetPath, JSON.stringify(target, null, 2) + "\n");

console.log(`Registered in ${targetPath}: ${registered.join(", ") || "(none)"}`);
console.log(`Skipped (missing secret/dependency): ${skipped.join(", ") || "(none)"}`);
