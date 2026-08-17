#!/usr/bin/env node

import { writeFileSync, readFileSync, mkdirSync, copyFileSync, existsSync, cpSync, chmodSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { homedir, platform } from 'node:os';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const HOST_NAME = 'com.chrome_bridge.native';
const EXTENSION_ID = 'nbghhppoiigjbdjbhefiaijofpnhgepb';
const isWindows = platform() === 'win32';

// Parse command line arguments
const args = process.argv.slice(2);
const command = args[0] || 'setup';

if (command === 'help' || command === '--help' || command === '-h') {
  console.log(`
Chrome Bridge CLI & Setup Tool

Usage:
  npx antigravity-chrome-bridge [command] [options]
  node setup-host.mjs [command] [options]

Commands:
  setup (default)    Install runtime, register Chrome native host, install skill, & configure MCP
  status             Check status of native messaging host, MCP config, and Python environment
  help               Show this help message

Options:
  --dev, --local     Configure host pointing directly to current directory instead of ~/.chrome-bridge
  --target <dir>     Specify custom target directory for runtime installation
`);
  process.exit(0);
}

// Determine installation directory
const isDevFlag = args.includes('--dev') || args.includes('--local');
const isNpxOrGlobal = __dirname.includes('node_modules') || __dirname.includes('_npx') || process.env.npm_config_global === 'true';
const targetDirIndex = args.indexOf('--target');
let customTarget = targetDirIndex !== -1 && args[targetDirIndex + 1] ? resolve(args[targetDirIndex + 1]) : null;

let INSTALL_DIR = customTarget;
if (!INSTALL_DIR) {
  if (isDevFlag) {
    INSTALL_DIR = __dirname;
  } else if (isNpxOrGlobal || !existsSync(join(__dirname, '.git'))) {
    INSTALL_DIR = join(homedir(), '.chrome-bridge');
  } else {
    // Local git clone default
    INSTALL_DIR = __dirname;
  }
}

if (command === 'status') {
  console.log('🔍 Checking Chrome Bridge Status...\n');
  console.log(`- Runtime Directory: ${INSTALL_DIR} (${existsSync(INSTALL_DIR) ? '✅ Exists' : '❌ Missing'})`);
  
  const venvDir = join(INSTALL_DIR, '.venv');
  const venvPy = isWindows ? join(venvDir, 'Scripts', 'python.exe') : join(venvDir, 'bin', 'python3');
  console.log(`- Python Environment: ${venvPy} (${existsSync(venvPy) ? '✅ Ready' : '⚠️ Missing/Unprovisioned'})`);

  const hostScript = join(INSTALL_DIR, 'native-host.mjs');
  console.log(`- Native Host Script: ${hostScript} (${existsSync(hostScript) ? '✅ Present' : '❌ Missing'})`);

  const agentSkill = join(homedir(), '.agent', 'skills', 'chrome-bridge', 'SKILL.md');
  console.log(`- Agent Skill: ${agentSkill} (${existsSync(agentSkill) ? '✅ Installed' : '⚠️ Missing'})`);

  process.exit(0);
}

console.log('🚀 Setting up Chrome Bridge across platforms...');
console.log(`📁 Target runtime location: ${INSTALL_DIR}\n`);

// 1. Sync runtime files if installing to an external/persistent directory
if (INSTALL_DIR !== __dirname) {
  mkdirSync(INSTALL_DIR, { recursive: true });
  
  const runtimeFiles = [
    'native-host.mjs',
    'mcp_server.py',
    'repl_engine.py',
    'chrome_sdk.py',
    'requirements.txt',
    'package.json',
    'pyproject.toml'
  ];

  for (const file of runtimeFiles) {
    const src = join(__dirname, file);
    const dst = join(INSTALL_DIR, file);
    if (existsSync(src)) {
      copyFileSync(src, dst);
    }
  }

  // Copy .agents and extension folders if present
  const dirsToCopy = ['.agents', 'extension'];
  for (const dir of dirsToCopy) {
    const srcDir = join(__dirname, dir);
    const dstDir = join(INSTALL_DIR, dir);
    if (existsSync(srcDir)) {
      cpSync(srcDir, dstDir, { recursive: true });
    }
  }

  console.log(`✅ Synced runtime files to: ${INSTALL_DIR}`);
}

// Ensure native-host.mjs is executable on POSIX systems
const targetNativeHostScript = join(INSTALL_DIR, 'native-host.mjs');
if (!isWindows && existsSync(targetNativeHostScript)) {
  try {
    chmodSync(targetNativeHostScript, 0o755);
  } catch {}
}

// 2. Resolve / Bootstrap Python Environment
function resolvePython() {
  const venvDir = join(INSTALL_DIR, '.venv');
  const venvPythonPosix = join(venvDir, 'bin', 'python3');
  const venvPythonWin = join(venvDir, 'Scripts', 'python.exe');

  if (isWindows && existsSync(venvPythonWin)) {
    return venvPythonWin;
  }
  if (!isWindows && existsSync(venvPythonPosix)) {
    return venvPythonPosix;
  }

  // Try auto-provisioning venv if not present
  try {
    console.log('📦 Setting up Python virtual environment (.venv)...');
    let hasUv = false;
    try {
      execSync('uv --version', { stdio: 'ignore' });
      hasUv = true;
    } catch {}

    const reqPath = join(INSTALL_DIR, 'requirements.txt');
    if (hasUv) {
      execSync(`uv venv "${venvDir}"`, { cwd: INSTALL_DIR, stdio: 'inherit' });
      execSync(`uv pip install -r "${reqPath}"`, { cwd: INSTALL_DIR, stdio: 'inherit' });
    } else {
      const pythonCmd = isWindows ? 'python' : 'python3';
      execSync(`${pythonCmd} -m venv "${venvDir}"`, { cwd: INSTALL_DIR, stdio: 'inherit' });
      const pipCmd = isWindows ? join(venvDir, 'Scripts', 'pip.exe') : join(venvDir, 'bin', 'pip');
      execSync(`"${pipCmd}" install -r "${reqPath}"`, { cwd: INSTALL_DIR, stdio: 'inherit' });
    }

    if (isWindows && existsSync(venvPythonWin)) return venvPythonWin;
    if (!isWindows && existsSync(venvPythonPosix)) return venvPythonPosix;
  } catch (err) {
    console.warn('⚠️ Could not automatically provision .venv:', err.message);
    console.warn('\nTo install Python 3.11+:');
    if (isWindows) {
      console.warn('  👉 winget install Python.Python.3.11');
    } else if (platform() === 'darwin') {
      console.warn('  👉 brew install python@3.11');
    } else {
      console.warn('  👉 sudo apt update && sudo apt install python3-venv python3-pip');
    }
    console.warn('');
  }

  // Fallback to system python with version verification
  const fallbackCmd = isWindows ? 'python.exe' : 'python3';
  try {
    const versionOutput = execSync(`"${fallbackCmd}" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"`, { encoding: 'utf8' }).trim();
    const [major, minor] = versionOutput.split('.').map(Number);
    if (major > 3 || (major === 3 && minor >= 10)) {
      return fallbackCmd;
    }
    console.warn(`⚠️ System ${fallbackCmd} version (${versionOutput}) is below required 3.10+`);
  } catch (err) {
    console.warn(`⚠️ Could not verify version of ${fallbackCmd}:`, err.message);
  }
  return fallbackCmd;
}

const PYTHON_CMD = resolvePython();
const HOST_SCRIPT = join(INSTALL_DIR, 'native-host.mjs');
const MCP_PYTHON_SCRIPT = join(INSTALL_DIR, 'mcp_server.py');

// 3. Register Native Messaging Host
let hostExecutablePath = HOST_SCRIPT;

if (isWindows) {
  // On Windows, Chrome requires an executable (.bat or .exe)
  const batPath = join(INSTALL_DIR, 'native-host.bat');
  const batContent = `@echo off\r\nnode "${HOST_SCRIPT}" %*\r\n`;
  try {
    writeFileSync(batPath, batContent);
    console.log(`✅ Generated Windows Host Batch Wrapper: ${batPath}`);
    hostExecutablePath = batPath;
  } catch (err) {
    console.warn('⚠️ Failed to generate native-host.bat:', err.message);
  }
}

const manifest = {
  name: HOST_NAME,
  description: 'Chrome Bridge Native Host',
  path: hostExecutablePath,
  type: 'stdio',
  allowed_origins: [
    `chrome-extension://${EXTENSION_ID}/`
  ]
};

if (isWindows) {
  // Windows Registration via Registry Keys
  const manifestDir = join(INSTALL_DIR);
  const manifestPath = join(manifestDir, `${HOST_NAME}.json`);
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  console.log(`✅ Wrote Windows Host Manifest: ${manifestPath}`);

  const regKeys = [
    `HKCU\\Software\\Google\\Chrome\\NativeMessagingHosts\\${HOST_NAME}`,
    `HKCU\\Software\\BraveSoftware\\Brave-Browser\\NativeMessagingHosts\\${HOST_NAME}`,
    `HKCU\\Software\\Microsoft\\Edge\\NativeMessagingHosts\\${HOST_NAME}`,
    `HKCU\\Software\\Chromium\\NativeMessagingHosts\\${HOST_NAME}`
  ];

  for (const key of regKeys) {
    try {
      execSync(`reg.exe add "${key}" /ve /t REG_SZ /d "${manifestPath}" /f`, { stdio: 'ignore' });
      console.log(`✅ Registered Windows Registry Host Key: ${key}`);
    } catch {
      // Ignore browsers not present or registry errors
    }
  }
} else {
  // Linux & macOS Registration via Manifest Directories
  const browserDirs = [
    // Linux
    join(homedir(), '.config', 'google-chrome', 'NativeMessagingHosts'),
    join(homedir(), '.config', 'chromium', 'NativeMessagingHosts'),
    join(homedir(), '.config', 'BraveSoftware', 'Brave-Browser', 'NativeMessagingHosts'),
    join(homedir(), '.config', 'microsoft-edge', 'NativeMessagingHosts'),
    // macOS
    join(homedir(), 'Library', 'Application Support', 'Google', 'Chrome', 'NativeMessagingHosts'),
    join(homedir(), 'Library', 'Application Support', 'Chromium', 'NativeMessagingHosts'),
    join(homedir(), 'Library', 'Application Support', 'BraveSoftware', 'Brave-Browser', 'NativeMessagingHosts'),
    join(homedir(), 'Library', 'Application Support', 'Microsoft Edge', 'NativeMessagingHosts')
  ];

  for (const dir of browserDirs) {
    try {
      mkdirSync(dir, { recursive: true });
      const targetPath = join(dir, `${HOST_NAME}.json`);
      writeFileSync(targetPath, JSON.stringify(manifest, null, 2));
      console.log(`✅ Registered Native Host: ${targetPath}`);
    } catch {}
  }
}

// 4. Install Agent Skill into ~/.agent/skills and ~/.gemini/...
const skillSource = join(INSTALL_DIR, '.agents', 'skills', 'chrome-bridge', 'SKILL.md');

if (existsSync(skillSource)) {
  const destDirs = [
    join(homedir(), '.agent', 'skills', 'chrome-bridge'),
    join(homedir(), '.gemini', 'antigravity-cli', 'skills', 'chrome-bridge')
  ];
  for (const destDir of destDirs) {
    try {
      mkdirSync(destDir, { recursive: true });
      copyFileSync(skillSource, join(destDir, 'SKILL.md'));
      console.log(`✅ Installed Agent Skill: ${join(destDir, 'SKILL.md')}`);
    } catch {}
  }
}

// 5. Automatically update MCP configurations across clients
function updateMcpConfig(filePath, clientName) {
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
    console.log(`✅ Auto-configured ${clientName} MCP (${PYTHON_CMD}): ${filePath}`);
    return true;
  } catch (err) {
    console.warn(`⚠️ Could not update ${filePath}:`, err.message);
    return false;
  }
}

// Update Antigravity / Gemini CLI MCP config
updateMcpConfig(join(homedir(), '.agent', 'mcp_config.json'), 'Antigravity');
updateMcpConfig(join(homedir(), '.gemini', 'antigravity-cli', 'mcp_config.json'), 'Antigravity CLI');

// Update Claude Desktop config
const appData = process.env.APPDATA || join(homedir(), 'AppData', 'Roaming');
const claudePaths = [
  join(homedir(), '.config', 'Claude', 'claude_desktop_config.json'),
  join(homedir(), 'Library', 'Application Support', 'Claude', 'claude_desktop_config.json'),
  join(appData, 'Claude', 'claude_desktop_config.json')
];

for (const p of claudePaths) {
  if (existsSync(dirname(p))) {
    updateMcpConfig(p, 'Claude Desktop');
  }
}

// Update Cursor MCP config if directory exists
const cursorPath = join(homedir(), '.cursor', 'mcp.json');
if (existsSync(dirname(cursorPath))) {
  updateMcpConfig(cursorPath, 'Cursor');
}

console.log('\n🎉 Setup complete! Chrome Bridge is ready for your AI assistants.');

