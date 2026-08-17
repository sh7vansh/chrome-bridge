#!/usr/bin/env node

import { writeFileSync, readFileSync, mkdirSync, copyFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const HOST_NAME = 'com.antigravity.chrome_bridge';
const EXTENSION_ID = 'nbghhppoiigjbdjbhefiaijofpnhgepb';
const HOST_SCRIPT = join(__dirname, 'native-host.mjs');
const MCP_PYTHON_SCRIPT = join(__dirname, 'mcp_server.py');
const VENV_PYTHON = join(__dirname, '.venv', 'bin', 'python3');
const PYTHON_CMD = existsSync(VENV_PYTHON) ? VENV_PYTHON : 'python3';

console.log('🚀 Setting up Chrome Bridge 2.0, Native Host & Python REPL MCP...\n');

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
  join(homedir(), 'Library', 'Application Support', 'Google', 'Chrome', 'NativeMessagingHosts'),
  join(homedir(), 'Library', 'Application Support', 'Chromium', 'NativeMessagingHosts'),
  join(homedir(), 'Library', 'Application Support', 'BraveSoftware', 'Brave-Browser', 'NativeMessagingHosts')
];

for (const dir of browserDirs) {
  try {
    mkdirSync(dir, { recursive: true });
    const targetPath = join(dir, `${HOST_NAME}.json`);
    writeFileSync(targetPath, JSON.stringify(manifest, null, 2));
    console.log(`✅ Registered Native Host: ${targetPath}`);
  } catch {}
}

// 2. Install Agent Skill into ~/.agent/skills
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

// 3. Automatically update MCP configurations
function updateMcpConfig(filePath) {
  try {
    let config = { mcpServers: {} };
    if (existsSync(filePath)) {
      try {
        const raw = readFileSync(filePath, 'utf8');
        config = JSON.parse(raw) || { mcpServers: {} };
        if (!config.mcpServers) config.mcpServers = {};
      } catch {
        config = { mcpServers: {} };
      }
    } else {
      mkdirSync(dirname(filePath), { recursive: true });
    }

    config.mcpServers['chrome-bridge'] = {
      command: PYTHON_CMD,
      args: [MCP_PYTHON_SCRIPT]
    };

    writeFileSync(filePath, JSON.stringify(config, null, 2) + '\n');
    console.log(`✅ Auto-configured MCP Server (${PYTHON_CMD}): ${filePath}`);
    return true;
  } catch (err) {
    console.warn(`⚠️ Could not update ${filePath}:`, err.message);
    return false;
  }
}

// Update Antigravity / Gemini CLI MCP config
updateMcpConfig(join(homedir(), '.agent', 'mcp_config.json'));

// Update Claude Desktop config if installed
const claudePaths = [
  join(homedir(), '.config', 'Claude', 'claude_desktop_config.json'),
  join(homedir(), 'Library', 'Application Support', 'Claude', 'claude_desktop_config.json'),
  join(homedir(), 'AppData', 'Roaming', 'Claude', 'claude_desktop_config.json')
];

for (const p of claudePaths) {
  if (existsSync(dirname(p))) {
    updateMcpConfig(p);
  }
}

console.log('\n🎉 Setup complete! Chrome Bridge 2.0 is fully configured for your AI assistants.');
