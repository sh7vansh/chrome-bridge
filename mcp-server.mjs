#!/usr/bin/env node

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import net from 'node:net';
import { writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const SOCKET_PATH = '/tmp/chrome_bridge.sock';
let reqId = 1;

/**
 * Send an RPC action to Chrome via Native Messaging Unix Domain Socket
 */
async function callChrome(action, params = {}, timeoutMs = 12000) {
  const id = reqId++;
  const payload = JSON.stringify({ id, action, params }) + '\n';

  return new Promise((resolve, reject) => {
    let client;
    let timer;
    let buffer = '';
    let settled = false;

    function cleanup() {
      if (timer) clearTimeout(timer);
      if (client) {
        client.removeAllListeners();
        client.destroy();
      }
    }

    function finish(err, res) {
      if (settled) return;
      settled = true;
      cleanup();
      if (err) reject(err);
      else resolve(res);
    }

    timer = setTimeout(() => {
      finish(new Error(`Action "${action}" timed out after ${timeoutMs / 1000}s. Ensure Google Chrome is open with the Antigravity Bridge extension loaded.`));
    }, timeoutMs);

    // Try connecting to Native Host Unix socket with short retry for cold starts
    let retries = 0;
    function tryConnect() {
      if (settled) return;

      client = net.connect(SOCKET_PATH);

      client.on('connect', () => {
        client.write(payload);
      });

      client.on('data', (chunk) => {
        buffer += chunk.toString('utf8');
        const lines = buffer.split('\n');
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const data = JSON.parse(line);
            if (data.id === id) {
              if (data.success) {
                finish(null, data.result);
              } else {
                finish(new Error(data.error || 'Unknown Chrome extension error'));
              }
              return;
            }
          } catch {}
        }
      });

      client.on('error', (err) => {
        if (err.code === 'ENOENT' || err.code === 'ECONNREFUSED') {
          if (retries < 15) {
            retries++;
            setTimeout(tryConnect, 200);
            return;
          }
          finish(new Error('Cannot connect to Chrome Native Bridge. Please make sure Google Chrome is open with the Antigravity extension enabled.'));
        } else {
          finish(err);
        }
      });
    }

    tryConnect();
  });
}

// Initialize MCP Server
const server = new McpServer({
  name: 'chrome-bridge',
  version: '1.0.0'
});

// Tool: Status
server.tool(
  'chrome_status',
  'Check connection status of Google Chrome Native Messaging Bridge',
  {},
  async () => {
    try {
      const ping = await callChrome('ping', {}, 3000);
      return {
        content: [{
          type: 'text',
          text: JSON.stringify({
            connected: true,
            transport: 'Chrome Native Messaging (stdio/IPC)',
            timestamp: ping.timestamp,
            message: 'Chrome is connected via Native Messaging Host.'
          }, null, 2)
        }]
      };
    } catch (err) {
      return {
        content: [{
          type: 'text',
          text: JSON.stringify({
            connected: false,
            transport: 'Chrome Native Messaging',
            error: err.message
          }, null, 2)
        }]
      };
    }
  }
);

// Tool: List Tabs
server.tool(
  'chrome_list_tabs',
  'List all open tabs in Google Chrome with tab ID, URL, title, and active status',
  {},
  async () => {
    const tabs = await callChrome('list_tabs');
    return {
      content: [{
        type: 'text',
        text: JSON.stringify(tabs, null, 2)
      }]
    };
  }
);

// Tool: Get Active Tab
server.tool(
  'chrome_get_active_tab',
  'Get details (tabId, URL, title) of the currently active/focused tab in Google Chrome',
  {},
  async () => {
    const tab = await callChrome('get_active_tab');
    return {
      content: [{
        type: 'text',
        text: JSON.stringify(tab || { message: 'No active tab found' }, null, 2)
      }]
    };
  }
);

// Tool: Navigate
server.tool(
  'chrome_navigate',
  'Navigate a tab to a specified URL, or open the URL in a new tab',
  {
    url: z.string().describe('Target URL to open (e.g. https://www.google.com)'),
    newTab: z.boolean().optional().describe('If true, opens in a brand new tab instead of navigating current tab'),
    tabId: z.number().optional().describe('Optional specific tab ID to navigate')
  },
  async ({ url, newTab = false, tabId }) => {
    const result = await callChrome('navigate', { url, newTab, tabId });
    return {
      content: [{
        type: 'text',
        text: JSON.stringify(result, null, 2)
      }]
    };
  }
);

// Tool: Get Page Content
server.tool(
  'chrome_get_page_content',
  'Extract semantic text, primary headings, title, and form inputs from the active (or specified) tab',
  {
    tabId: z.number().optional().describe('Optional specific tab ID')
  },
  async ({ tabId }) => {
    const content = await callChrome('get_page_content', { tabId });
    return {
      content: [{
        type: 'text',
        text: JSON.stringify(content, null, 2)
      }]
    };
  }
);

// Tool: Click
server.tool(
  'chrome_click',
  'Click a DOM element matching a CSS selector in the active tab',
  {
    selector: z.string().describe('CSS selector for element to click (e.g. button[type="submit"], a.btn)'),
    tabId: z.number().optional().describe('Optional specific tab ID')
  },
  async ({ selector, tabId }) => {
    const result = await callChrome('click', { selector, tabId });
    return {
      content: [{
        type: 'text',
        text: JSON.stringify(result, null, 2)
      }]
    };
  }
);

// Tool: Type
server.tool(
  'chrome_type',
  'Type text into an input or textarea element matching a CSS selector',
  {
    selector: z.string().describe('CSS selector for input element (e.g. input[name="q"])'),
    text: z.string().describe('Text to type into the element'),
    clear: z.boolean().optional().describe('Whether to clear existing text before typing (default: true)'),
    pressEnter: z.boolean().optional().describe('Whether to press Enter / submit form after typing (default: false)'),
    tabId: z.number().optional().describe('Optional specific tab ID')
  },
  async ({ selector, text, clear = true, pressEnter = false, tabId }) => {
    const result = await callChrome('type', { selector, text, clear, pressEnter, tabId });
    return {
      content: [{
        type: 'text',
        text: JSON.stringify(result, null, 2)
      }]
    };
  }
);

// Tool: Scroll
server.tool(
  'chrome_scroll',
  'Scroll the active tab page vertically and horizontally',
  {
    y: z.number().optional().describe('Vertical scroll distance in pixels (default: 500)'),
    x: z.number().optional().describe('Horizontal scroll distance in pixels (default: 0)'),
    tabId: z.number().optional().describe('Optional specific tab ID')
  },
  async ({ y = 500, x = 0, tabId }) => {
    const result = await callChrome('scroll', { x, y, tabId });
    return {
      content: [{
        type: 'text',
        text: JSON.stringify(result, null, 2)
      }]
    };
  }
);

// Tool: Screenshot
server.tool(
  'chrome_screenshot',
  'Capture a visual screenshot of the active tab. Saves to a local temporary file and returns path',
  {
    filePath: z.string().optional().describe('Destination file path (defaults to /tmp/chrome_tab_<timestamp>.png)'),
    tabId: z.number().optional().describe('Optional specific tab ID')
  },
  async ({ filePath, tabId }) => {
    const result = await callChrome('screenshot', { tabId });
    const base64Data = result.dataUrl.replace(/^data:image\/[a-z]+;base64,/, '');
    const outPath = filePath || join(tmpdir(), `chrome_tab_${Date.now()}.png`);
    writeFileSync(outPath, Buffer.from(base64Data, 'base64'));

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            success: true,
            filePath: outPath,
            sizeBytes: Buffer.byteLength(base64Data, 'base64')
          }, null, 2)
        }
      ]
    };
  }
);

// Tool: Execute Script
server.tool(
  'chrome_execute_script',
  'Execute arbitrary JavaScript in the active tab context and return evaluated result',
  {
    code: z.string().describe('JavaScript code to evaluate in the page'),
    tabId: z.number().optional().describe('Optional specific tab ID')
  },
  async ({ code, tabId }) => {
    const result = await callChrome('execute_script', { code, tabId });
    return {
      content: [{
        type: 'text',
        text: typeof result === 'string' ? result : JSON.stringify(result, null, 2)
      }]
    };
  }
);

// Tool: Switch Tab
server.tool(
  'chrome_switch_tab',
  'Focus and switch to a specific tab by ID',
  {
    tabId: z.number().describe('Tab ID to focus')
  },
  async ({ tabId }) => {
    const result = await callChrome('switch_tab', { tabId });
    return {
      content: [{
        type: 'text',
        text: JSON.stringify(result, null, 2)
      }]
    };
  }
);

// Tool: Close Tab
server.tool(
  'chrome_close_tab',
  'Close a tab by tab ID (or the active tab if omitted)',
  {
    tabId: z.number().optional().describe('Tab ID to close (closes active tab if omitted)')
  },
  async ({ tabId }) => {
    const result = await callChrome('close_tab', { tabId });
    return {
      content: [{
        type: 'text',
        text: JSON.stringify(result, null, 2)
      }]
    };
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  console.error('Fatal MCP server error:', err);
  process.exit(1);
});
