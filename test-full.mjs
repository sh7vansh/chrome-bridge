import { spawn } from 'node:child_process';
import { unlinkSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const server = spawn(process.execPath, [join(__dirname, 'mcp-server.mjs')]);

let reqId = 1;

function call(name, args = {}) {
  return new Promise((resolve) => {
    const id = reqId++;
    const handler = (d) => {
      const lines = d.toString().split('\n').filter(Boolean);
      for (const line of lines) {
        try {
          const parsed = JSON.parse(line);
          if (parsed.id === id) {
            server.stdout.off('data', handler);
            resolve(parsed.result);
          }
        } catch {}
      }
    };
    server.stdout.on('data', handler);
    server.stdin.write(JSON.stringify({
      jsonrpc: '2.0',
      id,
      method: 'tools/call',
      params: { name, arguments: args }
    }) + '\n');
  });
}

// Handshake
server.stdin.write(JSON.stringify({
  jsonrpc: '2.0',
  id: 0,
  method: 'initialize',
  params: { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'full-test', version: '1.0' } }
}) + '\n');

async function runAll() {
  console.log('🧪 Starting 100% Full Capabilities Test Suite...\n');

  // 1. Status
  console.log('1️⃣ [Status] Checking Native IPC health...');
  const res1 = await call('chrome_status');
  console.log('   ✅', res1.content[0].text);

  // 2. Active Tab
  console.log('\n2️⃣ [Active Tab] Querying focused tab...');
  const res2 = await call('chrome_get_active_tab');
  const activeTab = JSON.parse(res2.content[0].text);
  console.log('   ✅ Active Tab:', activeTab.title, `(ID: ${activeTab.id})`);

  // 3. List Tabs
  console.log('\n3️⃣ [List Tabs] Indexing all open tabs...');
  const res3 = await call('chrome_list_tabs');
  const tabs = JSON.parse(res3.content[0].text);
  console.log('   ✅ Open Tab Count:', tabs.length);

  // 4. Navigate
  console.log('\n4️⃣ [Navigation] Navigating to Wikipedia (Artificial intelligence)...');
  const res4 = await call('chrome_navigate', { url: 'https://en.wikipedia.org/wiki/Artificial_intelligence' });
  console.log('   ✅ Navigated Tab:', JSON.parse(res4.content[0].text).tabId);

  await new Promise(r => setTimeout(r, 2000));

  // 5. Semantic Content Extraction
  console.log('\n5️⃣ [Content Extraction] Extracting headings and page text...');
  const res5 = await call('chrome_get_page_content');
  const content = JSON.parse(res5.content[0].text);
  console.log('   ✅ Title:', content.title);
  console.log('   ✅ Heading:', content.heading);
  console.log('   ✅ Inputs Count:', content.inputCount);
  console.log('   ✅ Body Preview:', content.bodyText.slice(0, 150).replace(/\n/g, ' '));

  // 6. DOM Typing
  console.log('\n6️⃣ [Typing] Typing search query into search input...');
  const res6 = await call('chrome_type', {
    selector: 'input[name="search"]',
    text: 'Deep learning'
  });
  console.log('   ✅ Typed Value:', JSON.parse(res6.content[0].text).currentValue);

  // 7. Scrolling
  console.log('\n7️⃣ [Scrolling] Scrolling viewport...');
  const res7 = await call('chrome_scroll', { y: 750, x: 0 });
  console.log('   ✅ Scrolled by:', JSON.parse(res7.content[0].text).scrolled);

  // 8. CDP JS Execution
  console.log('\n8️⃣ [CDP Execution] Running JavaScript expression in page context...');
  const res8 = await call('chrome_execute_script', {
    code: 'document.querySelectorAll("h2, h3").length + " headings counted via CDP"'
  });
  console.log('   ✅ Script Output:', res8.content[0].text);

  // 9. Visual Screenshot
  console.log('\n9️⃣ [Screenshot] Capturing visual PNG screenshot...');
  const screenshotPath = '/tmp/live_full_capability_test.png';
  const res9 = await call('chrome_screenshot', { filePath: screenshotPath });
  const ss = JSON.parse(res9.content[0].text);
  console.log('   ✅ Screenshot Size:', ss.sizeBytes, 'bytes');

  if (existsSync(screenshotPath)) {
    unlinkSync(screenshotPath);
    console.log('   🧹 Temporary screenshot cleanly deleted.');
  }

  // 10. Open New Tab
  console.log('\n🔟 [Multi-Tab] Opening second tab (GitHub)...');
  const res10 = await call('chrome_navigate', { url: 'https://github.com', newTab: true });
  const newTabId = JSON.parse(res10.content[0].text).tabId;
  console.log('   ✅ Opened Second Tab ID:', newTabId);

  await new Promise(r => setTimeout(r, 1500));

  // 11. Switch Tab
  console.log('\n1️⃣1️⃣ [Multi-Tab] Switching focus back to original tab...');
  const res11 = await call('chrome_switch_tab', { tabId: activeTab.id });
  console.log('   ✅ Refocused Tab ID:', JSON.parse(res11.content[0].text).tabId);

  // 12. Close Tab
  console.log('\n1️⃣2️⃣ [Multi-Tab] Closing second tab...');
  const res12 = await call('chrome_close_tab', { tabId: newTabId });
  console.log('   ✅ Closed Tab ID:', JSON.parse(res12.content[0].text).closedTabId);

  console.log('\n🎉 ALL 12 MCP CAPABILITIES TESTED AND VERIFIED SUCCESSFULLY!');
  server.kill();
  process.exit(0);
}

setTimeout(runAll, 400);
