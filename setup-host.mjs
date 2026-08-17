#!/usr/bin/env node

/**
 * Chrome Bridge - Host Registration & Setup CLI
 * 
 * Configures:
 * 1. Persistent runtime directory (~/.chrome-bridge or workspace)
 * 2. Python 3.11+ virtual environment & dependencies
 * 3. Chrome / Chromium / Brave / Edge Native Messaging Host
 * 4. Antigravity AI Agent Skills
 * 5. MCP Server configurations across Antigravity, Claude Desktop, and Cursor
 */

import { writeFileSync, readFileSync, mkdirSync, copyFileSync, existsSync, cpSync, chmodSync, statSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { homedir, platform, arch, release } from 'node:os';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const HOST_NAME = 'com.chrome_bridge.native';
const EXTENSION_ID = 'nbghhppoiigjbdjbhefiaijofpnhgepb';
const isWindows = platform() === 'win32';
const isMac = platform() === 'darwin';
const isLinux = platform() === 'linux';

// ANSI Formatting helpers
const supportsColor = !process.env.NO_COLOR && (process.stdout.isTTY || process.env.FORCE_COLOR);
const c = {
  reset: supportsColor ? '\x1b[0m' : '',
  bold: supportsColor ? '\x1b[1m' : '',
  dim: supportsColor ? '\x1b[2m' : '',
  cyan: supportsColor ? '\x1b[36m' : '',
  green: supportsColor ? '\x1b[32m' : '',
  yellow: supportsColor ? '\x1b[33m' : '',
  magenta: supportsColor ? '\x1b[35m' : '',
  blue: supportsColor ? '\x1b[34m' : '',
  red: supportsColor ? '\x1b[31m' : ''
};

function banner() {
  console.log(`${c.bold}${c.cyan}================================================================${c.reset}`);
  console.log(`${c.bold}${c.cyan}   🌐 Chrome Bridge 2.0 — Setup & Environment Provisioner        ${c.reset}`);
  console.log(`${c.bold}${c.cyan}================================================================${c.reset}`);
}

// Parse command line arguments
const args = process.argv.slice(2);
const command = args.find(arg => !arg.startsWith('-')) || 'setup';

if (args.includes('help') || args.includes('--help') || args.includes('-h')) {
  banner();
  console.log(`
${c.bold}USAGE:${c.reset}
  npx antigravity-chrome-bridge [command] [options]
  node setup-host.mjs [command] [options]

${c.bold}COMMANDS:${c.reset}
  ${c.green}setup${c.reset} (default)    Install runtime, bootstrap Python, register Native Host & MCP
  ${c.green}status${c.reset}             Check status of native host, virtualenv, skills, and MCP
  ${c.green}help${c.reset}               Display this help guide

${c.bold}OPTIONS:${c.reset}
  ${c.yellow}--dev, --local${c.reset}     Configure host pointing directly to current directory
  ${c.yellow}--target <dir>${c.reset}     Specify a custom installation root directory
  ${c.yellow}--quiet${c.reset}            Suppress detailed logs and display summary only

${c.bold}EXAMPLES:${c.reset}
  ${c.dim}# 1-step installation via npx${c.reset}
  npx antigravity-chrome-bridge setup

  ${c.dim}# Verify current installation & diagnostics${c.reset}
  npx antigravity-chrome-bridge status
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
    INSTALL_DIR = __dirname;
  }
}

// -----------------------------------------------------------------------------
// STATUS / DIAGNOSTICS SUBCOMMAND
// -----------------------------------------------------------------------------
if (command === 'status') {
  banner();
  console.log(`\n${c.bold}🔍 System & Runtime Diagnostics:${c.reset}\n`);
  
  console.log(`  ${c.bold}Platform:${c.reset}       ${platform()} (${arch()}) - Release ${release()}`);
  console.log(`  ${c.bold}Node.js:${c.reset}        ${process.version} (${process.execPath})`);
  console.log(`  ${c.bold}Runtime Root:${c.reset}   ${INSTALL_DIR} ${existsSync(INSTALL_DIR) ? `${c.green}[Found]${c.reset}` : `${c.red}[Missing]${c.reset}`}`);

  const venvDir = join(INSTALL_DIR, '.venv');
  const venvPy = isWindows ? join(venvDir, 'Scripts', 'python.exe') : join(venvDir, 'bin', 'python3');
  const hasVenv = existsSync(venvPy);
  console.log(`  ${c.bold}Python venv:${c.reset}    ${venvPy} ${hasVenv ? `${c.green}[Active]${c.reset}` : `${c.yellow}[Not Provisioned]${c.reset}`}`);
  
  if (hasVenv) {
    try {
      const pyVer = execSync(`"${venvPy}" --version`, { encoding: 'utf8' }).trim();
      console.log(`    ↳ ${c.dim}${pyVer}${c.reset}`);
    } catch {}
  }

  const hostScript = join(INSTALL_DIR, 'native-host.mjs');
  console.log(`  ${c.bold}Native Host:${c.reset}    ${hostScript} ${existsSync(hostScript) ? `${c.green}[Present]${c.reset}` : `${c.red}[Missing]${c.reset}`}`);

  const mcpServer = join(INSTALL_DIR, 'mcp_server.py');
  console.log(`  ${c.bold}MCP Server:${c.reset}     ${mcpServer} ${existsSync(mcpServer) ? `${c.green}[Present]${c.reset}` : `${c.red}[Missing]${c.reset}`}`);

  const agentSkill = join(homedir(), '.agent', 'skills', 'chrome-bridge', 'SKILL.md');
  console.log(`  ${c.bold}Agent Skill:${c.reset}    ${agentSkill} ${existsSync(agentSkill) ? `${c.green}[Installed]${c.reset}` : `${c.yellow}[Not Installed]${c.reset}`}`);

  console.log(`\n${c.bold}🌐 Browser Native Messaging Manifests:${c.reset}`);
  const testPaths = [
    join(homedir(), '.config', 'google-chrome', 'NativeMessagingHosts', `${HOST_NAME}.json`),
    join(homedir(), '.config', 'chromium', 'NativeMessagingHosts', `${HOST_NAME}.json`),
    join(homedir(), '.config', 'BraveSoftware', 'Brave-Browser', 'NativeMessagingHosts', `${HOST_NAME}.json`),
    join(homedir(), '.config', 'microsoft-edge', 'NativeMessagingHosts', `${HOST_NAME}.json`),
    join(homedir(), 'Library', 'Application Support', 'Google', 'Chrome', 'NativeMessagingHosts', `${HOST_NAME}.json`)
  ];

  let foundManifests = 0;
  for (const tp of testPaths) {
    if (existsSync(tp)) {
      console.log(`  ${c.green}✓${c.reset} ${tp}`);
      foundManifests++;
    }
  }
  if (foundManifests === 0 && !isWindows) {
    console.log(`  ${c.yellow}⚠️ No browser native messaging manifests found in default paths.${c.reset}`);
  }

  console.log(`\n${c.bold}🤖 MCP Client Configurations:${c.reset}`);
  const mcpConfigs = [
    { name: 'Antigravity', path: join(homedir(), '.agent', 'mcp_config.json') },
    { name: 'Antigravity CLI', path: join(homedir(), '.gemini', 'antigravity-cli', 'mcp_config.json') },
    { name: 'Claude Desktop', path: join(homedir(), '.config', 'Claude', 'claude_desktop_config.json') },
    { name: 'Cursor', path: join(homedir(), '.cursor', 'mcp.json') }
  ];

  for (const cfg of mcpConfigs) {
    if (existsSync(cfg.path)) {
      try {
        const content = JSON.parse(readFileSync(cfg.path, 'utf8'));
        const hasChromeBridge = content.mcpServers && content.mcpServers['chrome-bridge'];
        console.log(`  ${hasChromeBridge ? c.green + '✓' : c.yellow + '○'}${c.reset} ${cfg.name}: ${cfg.path} ${hasChromeBridge ? `${c.green}(Configured)${c.reset}` : `${c.yellow}(Missing chrome-bridge entry)${c.reset}`}`);
      } catch {
        console.log(`  ${c.yellow}○${c.reset} ${cfg.name}: ${cfg.path} ${c.dim}(Unparseable JSON)${c.reset}`);
      }
    } else {
      console.log(`  ${c.dim}- ${cfg.name}: ${cfg.path} (Not present on system)${c.reset}`);
    }
  }

  console.log('\n');
  process.exit(0);
}

// -----------------------------------------------------------------------------
// SETUP EXECUTION
// -----------------------------------------------------------------------------
banner();

console.log(`\n${c.bold}📋 System Environment & Execution Context:${c.reset}`);
console.log(`  • Operating System:  ${platform()} (${arch()}) [${isWindows ? 'Windows' : isMac ? 'macOS' : 'Linux'}]`);
console.log(`  • Node.js Version:   ${process.version}`);
console.log(`  • Script Source:     ${__dirname}`);
console.log(`  • Target Runtime:    ${c.bold}${c.cyan}${INSTALL_DIR}${c.reset}`);
console.log(`  • Extension ID:      ${c.bold}${EXTENSION_ID}${c.reset}`);
console.log(`  • Native Host Name:  ${c.bold}${HOST_NAME}${c.reset}\n`);

// 1. Sync runtime files if installing to an external/persistent directory
console.log(`${c.bold}${c.yellow}[1/5] Synchronizing Runtime Files & Assets...${c.reset}`);
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
      const size = statSync(dst).size;
      console.log(`  ${c.green}✓${c.reset} Synced ${c.bold}${file}${c.reset} ${c.dim}(${size} bytes)${c.reset}`);
    }
  }

  // Copy .agents and extension folders if present
  const dirsToCopy = ['.agents', 'extension'];
  for (const dir of dirsToCopy) {
    const srcDir = join(__dirname, dir);
    const dstDir = join(INSTALL_DIR, dir);
    if (existsSync(srcDir)) {
      cpSync(srcDir, dstDir, { recursive: true });
      console.log(`  ${c.green}✓${c.reset} Synced directory ${c.bold}${dir}/${c.reset}`);
    }
  }
} else {
  console.log(`  ${c.green}✓${c.reset} Running directly from repository source directory.`);
}

// Ensure native-host.mjs is executable on POSIX systems
const targetNativeHostScript = join(INSTALL_DIR, 'native-host.mjs');
if (!isWindows && existsSync(targetNativeHostScript)) {
  try {
    chmodSync(targetNativeHostScript, 0o755);
    console.log(`  ${c.green}✓${c.reset} Set executable permissions (0755) on ${targetNativeHostScript}`);
  } catch (err) {
    console.warn(`  ${c.yellow}⚠️ Could not chmod native-host.mjs:${c.reset}`, err.message);
  }
}

// 2. Resolve / Bootstrap Python Environment
console.log(`\n${c.bold}${c.yellow}[2/5] Provisioning Python Virtual Environment (.venv)...${c.reset}`);

function resolvePython() {
  const venvDir = join(INSTALL_DIR, '.venv');
  const venvPythonPosix = join(venvDir, 'bin', 'python3');
  const venvPythonWin = join(venvDir, 'Scripts', 'python.exe');

  if (isWindows && existsSync(venvPythonWin)) {
    console.log(`  ${c.green}✓${c.reset} Reusing existing Python venv: ${venvPythonWin}`);
    return venvPythonWin;
  }
  if (!isWindows && existsSync(venvPythonPosix)) {
    console.log(`  ${c.green}✓${c.reset} Reusing existing Python venv: ${venvPythonPosix}`);
    return venvPythonPosix;
  }

  try {
    let hasUv = false;
    try {
      execSync('uv --version', { stdio: 'ignore' });
      hasUv = true;
    } catch {}

    const reqPath = join(INSTALL_DIR, 'requirements.txt');

    if (hasUv) {
      console.log(`  ⚡ Fast installer ${c.bold}uv${c.reset} detected. Provisioning virtualenv with uv...`);
      execSync(`uv venv "${venvDir}"`, { cwd: INSTALL_DIR, stdio: 'inherit' });
      console.log(`  📥 Installing Python dependencies from ${reqPath}...`);
      execSync(`uv pip install -r "${reqPath}"`, { cwd: INSTALL_DIR, stdio: 'inherit' });
    } else {
      const pythonCmd = isWindows ? 'python' : 'python3';
      console.log(`  🐍 Using standard ${c.bold}${pythonCmd} -m venv${c.reset} to create virtualenv...`);
      execSync(`${pythonCmd} -m venv "${venvDir}"`, { cwd: INSTALL_DIR, stdio: 'inherit' });
      const pipCmd = isWindows ? join(venvDir, 'Scripts', 'pip.exe') : join(venvDir, 'bin', 'pip');
      console.log(`  📥 Installing Python dependencies with pip...`);
      execSync(`"${pipCmd}" install -r "${reqPath}"`, { cwd: INSTALL_DIR, stdio: 'inherit' });
    }

    if (isWindows && existsSync(venvPythonWin)) {
      console.log(`  ${c.green}✓${c.reset} Python environment ready: ${venvPythonWin}`);
      return venvPythonWin;
    }
    if (!isWindows && existsSync(venvPythonPosix)) {
      console.log(`  ${c.green}✓${c.reset} Python environment ready: ${venvPythonPosix}`);
      return venvPythonPosix;
    }
  } catch (err) {
    console.warn(`  ${c.yellow}⚠️ Could not automatically provision .venv:${c.reset}`, err.message);
    console.warn(`\n  ${c.bold}To install Python manually:${c.reset}`);
    if (isWindows) {
      console.warn(`    👉 ${c.cyan}winget install Python.Python.3.11${c.reset}`);
    } else if (isMac) {
      console.warn(`    👉 ${c.cyan}brew install python@3.11${c.reset}`);
    } else {
      console.warn(`    👉 ${c.cyan}sudo apt update && sudo apt install python3-venv python3-pip${c.reset}`);
    }
    console.warn('');
  }

  // Fallback to system python with version check
  const fallbackCmd = isWindows ? 'python.exe' : 'python3';
  try {
    const versionOutput = execSync(`"${fallbackCmd}" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"`, { encoding: 'utf8' }).trim();
    const [major, minor] = versionOutput.split('.').map(Number);
    if (major > 3 || (major === 3 && minor >= 10)) {
      console.log(`  ${c.green}✓${c.reset} Fallback to system Python (${versionOutput}): ${fallbackCmd}`);
      return fallbackCmd;
    }
    console.warn(`  ${c.yellow}⚠️ System ${fallbackCmd} version (${versionOutput}) is below recommended 3.10+${c.reset}`);
  } catch (err) {
    console.warn(`  ${c.yellow}⚠️ Could not verify version of ${fallbackCmd}:${c.reset}`, err.message);
  }
  return fallbackCmd;
}

const PYTHON_CMD = resolvePython();
const HOST_SCRIPT = join(INSTALL_DIR, 'native-host.mjs');
const MCP_PYTHON_SCRIPT = join(INSTALL_DIR, 'mcp_server.py');

// 3. Register Native Messaging Host
console.log(`\n${c.bold}${c.yellow}[3/5] Registering Chrome Native Messaging Host...${c.reset}`);
let hostExecutablePath = HOST_SCRIPT;

if (isWindows) {
  const batPath = join(INSTALL_DIR, 'native-host.bat');
  const batContent = `@echo off\r\nsetlocal\r\nchcp 65001 >nul 2>&1\r\nset PYTHONIOENCODING=utf-8\r\nset PYTHONUTF8=1\r\nnode "${HOST_SCRIPT}" %*\r\n`;
  try {
    writeFileSync(batPath, batContent);
    console.log(`  ${c.green}✓${c.reset} Generated Windows Host Batch Wrapper: ${batPath}`);
    hostExecutablePath = batPath;
  } catch (err) {
    console.warn(`  ${c.yellow}⚠️ Failed to generate native-host.bat:${c.reset}`, err.message);
  }
}

const manifest = {
  name: HOST_NAME,
  description: 'Chrome Bridge Native Messaging Host for AI Procedural Automation',
  path: hostExecutablePath,
  type: 'stdio',
  allowed_origins: [
    `chrome-extension://${EXTENSION_ID}/`
  ]
};

if (isWindows) {
  const manifestDir = join(INSTALL_DIR);
  const manifestPath = join(manifestDir, `${HOST_NAME}.json`);
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  console.log(`  ${c.green}✓${c.reset} Wrote Windows Host Manifest: ${manifestPath}`);

  const regKeys = [
    `HKCU\\Software\\Google\\Chrome\\NativeMessagingHosts\\${HOST_NAME}`,
    `HKCU\\Software\\BraveSoftware\\Brave-Browser\\NativeMessagingHosts\\${HOST_NAME}`,
    `HKCU\\Software\\Microsoft\\Edge\\NativeMessagingHosts\\${HOST_NAME}`,
    `HKCU\\Software\\Chromium\\NativeMessagingHosts\\${HOST_NAME}`
  ];

  for (const key of regKeys) {
    try {
      execSync(`reg.exe add "${key}" /ve /t REG_SZ /d "${manifestPath}" /f`, { stdio: 'ignore' });
      console.log(`  ${c.green}✓${c.reset} Registered Windows Registry Key: ${c.dim}${key}${c.reset}`);
    } catch {}
  }
} else {
  const browserDirs = [
    // Linux
    { browser: 'Google Chrome', path: join(homedir(), '.config', 'google-chrome', 'NativeMessagingHosts') },
    { browser: 'Chromium', path: join(homedir(), '.config', 'chromium', 'NativeMessagingHosts') },
    { browser: 'Brave Browser', path: join(homedir(), '.config', 'BraveSoftware', 'Brave-Browser', 'NativeMessagingHosts') },
    { browser: 'Microsoft Edge', path: join(homedir(), '.config', 'microsoft-edge', 'NativeMessagingHosts') },
    // macOS
    { browser: 'Google Chrome (macOS)', path: join(homedir(), 'Library', 'Application Support', 'Google', 'Chrome', 'NativeMessagingHosts') },
    { browser: 'Chromium (macOS)', path: join(homedir(), 'Library', 'Application Support', 'Chromium', 'NativeMessagingHosts') },
    { browser: 'Brave (macOS)', path: join(homedir(), 'Library', 'Application Support', 'BraveSoftware', 'Brave-Browser', 'NativeMessagingHosts') },
    { browser: 'Edge (macOS)', path: join(homedir(), 'Library', 'Application Support', 'Microsoft Edge', 'NativeMessagingHosts') }
  ];

  for (const item of browserDirs) {
    try {
      mkdirSync(item.path, { recursive: true });
      const targetPath = join(item.path, `${HOST_NAME}.json`);
      writeFileSync(targetPath, JSON.stringify(manifest, null, 2));
      console.log(`  ${c.green}✓${c.reset} Configured ${c.bold}${item.browser}${c.reset} manifest: ${c.dim}${targetPath}${c.reset}`);
    } catch {}
  }
}

// 4. Install Agent Skill into ~/.agent/skills and ~/.gemini/...
console.log(`\n${c.bold}${c.yellow}[4/5] Installing Agent Skill (chrome-bridge)...${c.reset}`);
const skillSource = join(INSTALL_DIR, '.agents', 'skills', 'chrome-bridge', 'SKILL.md');

if (existsSync(skillSource)) {
  const destDirs = [
    { target: 'Antigravity Global Agent (.agents)', dir: join(homedir(), '.agents', 'skills', 'chrome-bridge') },
    { target: 'Antigravity Global Agent (.agent)', dir: join(homedir(), '.agent', 'skills', 'chrome-bridge') },
    { target: 'Gemini CLI Agent', dir: join(homedir(), '.gemini', 'antigravity-cli', 'skills', 'chrome-bridge') },
    { target: 'Gemini Config Skills', dir: join(homedir(), '.gemini', 'config', 'skills', 'chrome-bridge') }
  ];
  for (const item of destDirs) {
    try {
      mkdirSync(item.dir, { recursive: true });
      copyFileSync(skillSource, join(item.dir, 'SKILL.md'));
      console.log(`  ${c.green}✓${c.reset} Installed for ${c.bold}${item.target}${c.reset}: ${c.dim}${join(item.dir, 'SKILL.md')}${c.reset}`);
    } catch (err) {
      console.warn(`  ${c.yellow}⚠️ Could not install skill to ${item.dir}:${c.reset}`, err.message);
    }
  }
} else {
  console.log(`  ${c.yellow}⚠️ Skill file not found at ${skillSource}. Skipping skill copy.${c.reset}`);
}

// 5. Automatically update MCP configurations across clients
console.log(`\n${c.bold}${c.yellow}[5/5] Configuring Model Context Protocol (MCP) Clients...${c.reset}`);

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
    console.log(`  ${c.green}✓${c.reset} Configured ${c.bold}${clientName}${c.reset}: ${c.dim}${filePath}${c.reset}`);
    return true;
  } catch (err) {
    console.warn(`  ${c.yellow}⚠️ Could not update ${filePath}:${c.reset}`, err.message);
    return false;
  }
}

// Update Antigravity & Gemini CLI MCP configs
updateMcpConfig(join(homedir(), '.agent', 'mcp_config.json'), 'Antigravity Global MCP');
updateMcpConfig(join(homedir(), '.gemini', 'antigravity-cli', 'mcp_config.json'), 'Antigravity CLI MCP');

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

// -----------------------------------------------------------------------------
// SUMMARY & NEXT STEPS
// -----------------------------------------------------------------------------
console.log(`
${c.bold}${c.green}================================================================${c.reset}
${c.bold}${c.green}   🎉 Setup Complete! Chrome Bridge is Live & Ready.             ${c.reset}
${c.bold}${c.green}================================================================${c.reset}

${c.bold}🚀 NEXT STEPS TO CONNECT YOUR BROWSER:${c.reset}

  ${c.bold}1. Install or Load the Chrome Extension:${c.reset}
     • Option A (Chrome Web Store):
       👉 ${c.cyan}https://chromewebstore.google.com/detail/${EXTENSION_ID}${c.reset}
     • Option B (Unpacked Developer Mode):
       Open ${c.bold}chrome://extensions/${c.reset} in Chrome, toggle ${c.bold}Developer mode${c.reset},
       click ${c.bold}[Load unpacked]${c.reset}, and select:
       👉 ${c.cyan}${join(INSTALL_DIR, 'extension')}${c.reset}

  ${c.bold}2. Verify Connection:${c.reset}
     Click the Chrome Bridge extension icon in your browser toolbar.
     It should show ${c.green}● Connected to Native Host${c.reset}.

  ${c.bold}3. Control Browser from your AI Assistant:${c.reset}
     Your assistant can now procedurally automate your browser:
     ${c.dim}"Inspect open tabs and snapshot the active page"${c.reset}
`);


