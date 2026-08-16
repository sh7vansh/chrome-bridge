import { writeFileSync, unlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const PORT = process.env.PORT || 8765;
const BASE_URL = `http://127.0.0.1:${PORT}/api`;

const args = process.argv.slice(2);
const command = args[0];

if (!command || command === '--help' || command === '-h') {
  console.log(`
Antigravity Chrome Controller (ctl.mjs)

Usage:
  node ctl.mjs <command> [arguments...]

Commands:
  status                                 Check extension connection status
  tabs                                   List all open tabs
  active                                 Get currently active tab info
  nav <url> [--new]                      Navigate active or new tab
  click <selector>                       Click element matching CSS selector
  type <selector> <text> [--enter]       Type text into input
  content                                Get active tab summary & text
  screenshot [filepath] [--ttl=seconds]  Capture screenshot (defaults to /tmp RAM-backed)
  eval <code>                            Execute arbitrary JS in active tab
  close [tabId]                          Close active or specified tab
  scroll [y] [x]                         Scroll active page
`);
  process.exit(0);
}

async function request(endpoint, payload = null, method = 'POST') {
  try {
    const res = await fetch(`${BASE_URL}/${endpoint}`, {
      method: payload ? 'POST' : (method || 'GET'),
      headers: payload ? { 'Content-Type': 'application/json' } : {},
      body: payload ? JSON.stringify(payload) : undefined
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      console.error('❌ Error:', data.error || res.statusText);
      process.exit(1);
    }
    return data.result;
  } catch (err) {
    console.error('❌ Connection Error:', err.message);
    console.error('   Ensure the bridge server is running: `node bridge.mjs`');
    process.exit(1);
  }
}

async function run() {
  switch (command) {
    case 'status': {
      const res = await fetch(`http://127.0.0.1:${PORT}/api/status`);
      const data = await res.json();
      console.log('Bridge Server:', data.status === 'ok' ? '🟢 Online' : '🔴 Offline');
      console.log('Chrome Extension:', data.extensionConnected ? '🟢 Connected' : '🔴 Disconnected');
      break;
    }

    case 'tabs': {
      const tabs = await request('tabs', {}, 'GET');
      console.log(`\n📑 Open Tabs (${tabs.length}):`);
      for (const t of tabs) {
        const star = t.active ? '⭐' : '  ';
        console.log(` ${star} [ID: ${t.id}] ${t.title || 'Untitled'}\n     URL: ${t.url}`);
      }
      break;
    }

    case 'active': {
      const tab = await request('active-tab', {}, 'GET');
      if (!tab) console.log('No active tab.');
      else console.log(`⭐ Active Tab [ID: ${tab.id}]: "${tab.title}"\n   URL: ${tab.url}`);
      break;
    }

    case 'nav': {
      const url = args[1];
      if (!url) {
        console.error('Usage: node ctl.mjs nav <url>');
        process.exit(1);
      }
      const newTab = args.includes('--new');
      const result = await request('navigate', { url, newTab });
      console.log(`🌐 Navigated to: ${result.url} (Tab ID: ${result.tabId})`);
      break;
    }

    case 'click': {
      const selector = args[1];
      if (!selector) {
        console.error('Usage: node ctl.mjs click <selector>');
        process.exit(1);
      }
      const result = await request('click', { selector });
      console.log(`🖱️ Clicked <${result.tagName}>: "${result.text?.slice(0, 30) || selector}"`);
      break;
    }

    case 'type': {
      const selector = args[1];
      const text = args[2];
      if (!selector || text === undefined) {
        console.error('Usage: node ctl.mjs type <selector> <text> [--enter]');
        process.exit(1);
      }
      const pressEnter = args.includes('--enter');
      const result = await request('type', { selector, text, pressEnter });
      console.log(`⌨️ Typed "${text}" into ${selector} (Value: "${result.currentValue}")`);
      break;
    }

    case 'content': {
      const content = await request('content', {}, 'GET');
      console.log(`📄 Page: "${content.title}"\n🔗 URL:  ${content.url}`);
      if (content.heading) console.log(`📌 Header: ${content.heading}`);
      console.log(`\n--- Text Preview ---\n${content.bodyText.slice(0, 1000)}...`);
      break;
    }

    case 'screenshot': {
      const result = await request('screenshot', {});
      const base64Data = result.dataUrl.replace(/^data:image\/[a-z]+;base64,/, '');
      
      let outPath = args[1] && !args[1].startsWith('--') ? args[1] : join(tmpdir(), 'chrome_live_tab.png');
      writeFileSync(outPath, Buffer.from(base64Data, 'base64'));
      console.log(`📸 Screenshot saved to temporary storage: ${outPath}`);

      // Check if auto-delete TTL requested
      const ttlArg = args.find(a => a.startsWith('--ttl='));
      if (ttlArg) {
        const seconds = parseInt(ttlArg.split('=')[1], 10) || 30;
        console.log(`⏳ Auto-deleting in ${seconds} seconds...`);
        setTimeout(() => {
          try {
            unlinkSync(outPath);
            console.log(`🗑️ Auto-deleted temporary screenshot: ${outPath}`);
          } catch {}
        }, seconds * 1000);
      }
      break;
    }

    case 'eval': {
      const code = args.slice(1).join(' ');
      if (!code) {
        console.error('Usage: node ctl.mjs eval <code>');
        process.exit(1);
      }
      const result = await request('eval', { code });
      console.log('Output:', result);
      break;
    }

    case 'close': {
      const tabId = args[1] ? parseInt(args[1], 10) : undefined;
      const result = await request('close', { tabId });
      console.log(`🗑️ Closed tab ID: ${result.closedTabId}`);
      break;
    }

    case 'scroll': {
      const y = args[1] ? parseInt(args[1], 10) : 500;
      const x = args[2] ? parseInt(args[2], 10) : 0;
      await request('scroll', { x, y });
      console.log(`📜 Scrolled (x: ${x}, y: ${y})`);
      break;
    }

    default:
      console.error(`Unknown command: ${command}. Run with --help for available commands.`);
  }
}

run();
