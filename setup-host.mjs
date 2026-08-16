#!/usr/bin/env node

import { writeFileSync, mkdirSync, copyFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const HOST_NAME = 'com.antigravity.chrome_bridge';
const EXTENSION_ID = 'nbghhppoiigjbdjbhefiaijofpnhgepb';
const HOST_SCRIPT = join(__dirname, 'native-host.mjs');
const MCP_SCRIPT = join(__dirname, 'mcp-server.mjs');

console.log('🚀 Setting up Chrome Bridge & Agent Skill...\n');

// 1. Register Native Messaging Host
const manifest = {
  name: HOST_NAME,
  description: 'Antigravity Chrome Bridge Native Host',
  path: HOST_SCRIPT,
  type: 'stdio',
  allowed_origins: [
    `chrome-extension://${EXTENSION_ID}/`
  ]
};

const browserDirs = [
  join(homedir(), '.config', 'google-chrome', 'NativeMessagingHosts'),
  join(homedir(), '.config', 'chromium', 'NativeMessagingHosts'),
  join(homedir(), '.config', 'BraveSoftware', 'Brave-Browser', 'NativeMessagingHosts'),
  // macOS paths
  join(homedir(), 'Library', 'Application Support', 'Google', 'Chrome', 'NativeMessagingHosts')
];

let hostRegistered = false;
for (const dir of browserDirs) {
  try {
    mkdirSync(dir, { recursive: true });
    const targetPath = join(dir, `${HOST_NAME}.json`);
    writeFileSync(targetPath, JSON.stringify(manifest, null, 2));
    console.log(`✅ Registered Native Host: ${targetPath}`);
    hostRegistered = true;
  } catch (err) {
    // Ignore missing parent directories
  }
}

// 2. Install Agent Skill into user's ~/.agent/skills
const skillSource = join(__dirname, 'skills', 'chrome-bridge', 'SKILL.md');
if (existsSync(skillSource)) {
  const skillDestDir = join(homedir(), '.agent', 'skills', 'chrome-bridge');
  try {
    mkdirSync(skillDestDir, { recursive: true });
    copyFileSync(skillSource, join(skillDestDir, 'SKILL.md'));
    console.log(`✅ Installed Agent Skill: ${join(skillDestDir, 'SKILL.md')}`);
  } catch (err) {
    console.warn('⚠️ Could not copy skill to ~/.agent/skills:', err.message);
  }
}

console.log('\n🎉 Setup complete!\n');
console.log('--- AI Client Configuration ---');
console.log('Add this block to your MCP config (e.g. ~/.agent/mcp_config.json or claude_desktop_config.json):\n');
console.log(JSON.stringify({
  mcpServers: {
    "chrome-bridge": {
      "command": "node",
      "args": [MCP_SCRIPT]
    }
  }
}, null, 2));
console.log('\n-------------------------------\n');
