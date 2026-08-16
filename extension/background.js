const HOST_NAME = 'com.antigravity.chrome_bridge';
let nativePort = null;
let reconnectTimer = null;

async function updateBadge(status) {
  if (status === 'connected') {
    await chrome.action.setBadgeText({ text: 'ON' });
    await chrome.action.setBadgeBackgroundColor({ color: '#10B981' });
  } else if (status === 'connecting') {
    await chrome.action.setBadgeText({ text: '...' });
    await chrome.action.setBadgeBackgroundColor({ color: '#F59E0B' });
  } else {
    await chrome.action.setBadgeText({ text: 'OFF' });
    await chrome.action.setBadgeBackgroundColor({ color: '#64748B' });
  }
}

async function logActivity(message, type = 'info') {
  const { activityLogs = [] } = await chrome.storage.local.get('activityLogs');
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const newLog = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    timestamp: timeStr,
    message,
    type
  };
  const updatedLogs = [newLog, ...activityLogs].slice(0, 60);
  await chrome.storage.local.set({ activityLogs: updatedLogs });
}

function connectNative() {
  if (nativePort) return;

  updateBadge('connecting');
  try {
    nativePort = chrome.runtime.connectNative(HOST_NAME);
  } catch (err) {
    console.warn('[NativeBridge] Connection failed:', err);
    updateBadge('disconnected');
    scheduleReconnect();
    return;
  }

  updateBadge('connected');
  chrome.storage.local.set({ isConnected: true, lastConnected: Date.now() });
  logActivity('Native Messaging Bridge Connected', 'success');

  nativePort.onMessage.addListener(async (msg) => {
    if (msg.event === 'host_ready') {
      console.log('[NativeBridge] Native Host ready:', msg);
      return;
    }

    const { id, action, params = {} } = msg;
    console.log(`[NativeBridge] Received action: ${action}`, params);

    // Format descriptive log
    let logMsg = `Action: ${action}`;
    let logType = 'cmd';

    if (action === 'navigate') {
      logMsg = `Navigated to ${params.url?.slice(0, 45)}${params.url?.length > 45 ? '...' : ''}`;
      logType = 'nav';
    } else if (action === 'click') {
      logMsg = `Clicked "${params.selector}"`;
      logType = 'click';
    } else if (action === 'type') {
      logMsg = `Typed "${params.text?.slice(0, 25)}" into ${params.selector}`;
      logType = 'type';
    } else if (action === 'screenshot') {
      logMsg = 'Captured visible tab screenshot';
      logType = 'screenshot';
    } else if (action === 'get_page_content') {
      logMsg = 'Extracted page text & semantic DOM';
      logType = 'content';
    } else if (action === 'execute_script') {
      logMsg = `Evaluated JS: ${params.code?.slice(0, 35)}...`;
      logType = 'eval';
    } else if (action === 'list_tabs') {
      logMsg = 'Listed open tabs';
      logType = 'tabs';
    } else if (action === 'get_active_tab') {
      logMsg = 'Queried active tab details';
      logType = 'tabs';
    } else if (action === 'scroll') {
      logMsg = `Scrolled page (${params.x || 0}, ${params.y || 500})`;
      logType = 'scroll';
    }

    await logActivity(logMsg, logType);

    try {
      const result = await handleAction(action, params);
      if (id && nativePort) {
        nativePort.postMessage({ id, success: true, result });
      }
    } catch (err) {
      console.error(`[NativeBridge] Action ${action} failed:`, err);
      await logActivity(`Failed ${action}: ${err.message}`, 'error');
      if (id && nativePort) {
        nativePort.postMessage({ id, success: false, error: err.message });
      }
    }
  });

  nativePort.onDisconnect.addListener(() => {
    const lastErr = chrome.runtime.lastError?.message;
    console.log('[NativeBridge] Native Host disconnected:', lastErr || 'clean exit');
    nativePort = null;
    chrome.storage.local.set({ isConnected: false });
    updateBadge('disconnected');
    scheduleReconnect();
  });
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    connectNative();
  }, 5000);
}

// Keepalive alarm
chrome.alarms.create('nativeBridgeKeepAlive', { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'nativeBridgeKeepAlive') {
    if (!nativePort) {
      connectNative();
    }
  }
});

async function resolveTabId(specifiedId) {
  if (specifiedId) return specifiedId;
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (activeTab) return activeTab.id;
  const [anyTab] = await chrome.tabs.query({ active: true });
  if (anyTab) return anyTab.id;
  throw new Error('No active browser tab found');
}

async function handleAction(action, params) {
  switch (action) {
    case 'ping':
      return { pong: true, timestamp: Date.now() };

    case 'list_tabs': {
      const tabs = await chrome.tabs.query({});
      return tabs.map(t => ({
        id: t.id,
        url: t.url,
        title: t.title,
        active: t.active,
        windowId: t.windowId
      }));
    }

    case 'get_active_tab': {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      return tab ? { id: tab.id, url: tab.url, title: tab.title, favIconUrl: tab.favIconUrl } : null;
    }

    case 'navigate': {
      const { url, tabId, newTab = false } = params;
      if (!url) throw new Error('Missing "url" parameter');
      if (newTab) {
        const created = await chrome.tabs.create({ url, active: true });
        return { tabId: created.id, url: created.url };
      }
      const targetId = await resolveTabId(tabId);
      const updated = await chrome.tabs.update(targetId, { url });
      return { tabId: updated.id, url: updated.url };
    }

    case 'switch_tab': {
      const targetId = await resolveTabId(params.tabId);
      const tab = await chrome.tabs.update(targetId, { active: true });
      await chrome.windows.update(tab.windowId, { focused: true });
      return { success: true, tabId: targetId };
    }

    case 'close_tab': {
      const targetId = await resolveTabId(params.tabId);
      await chrome.tabs.remove(targetId);
      return { success: true, closedTabId: targetId };
    }

    case 'screenshot': {
      const targetId = await resolveTabId(params.tabId);
      const tab = await chrome.tabs.get(targetId);
      const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
      return { dataUrl };
    }

    case 'execute_script': {
      const { code, tabId } = params;
      if (!code) throw new Error('Missing "code" parameter');
      const targetId = await resolveTabId(tabId);

      // Method 1: Chrome DevTools Protocol (Runtime.evaluate) — bypasses all website CSPs
      const target = { tabId: targetId };
      try {
        await chrome.debugger.attach(target, '1.3');
        const evalRes = await chrome.debugger.sendCommand(target, 'Runtime.evaluate', {
          expression: code,
          returnByValue: true,
          awaitPromise: true
        });
        await chrome.debugger.detach(target);

        if (evalRes.exceptionDetails) {
          throw new Error(evalRes.exceptionDetails.exception?.description || evalRes.exceptionDetails.text);
        }
        return evalRes.result?.value;
      } catch (dbgErr) {
        try { await chrome.debugger.detach(target); } catch {}

        // Method 2: Fallback for special URLs or environments where debugger is restricted
        const results = await chrome.scripting.executeScript({
          target: { tabId: targetId },
          world: 'MAIN',
          func: (expression) => {
            if (expression === 'document.title') return document.title;
            if (expression === 'location.href' || expression === 'window.location.href') return window.location.href;
            try {
              return (0, eval)(expression);
            } catch (e) {
              return { __error: e.message };
            }
          },
          args: [code]
        });

        const execResult = results[0]?.result;
        if (execResult && typeof execResult === 'object' && execResult.__error) {
          throw new Error(execResult.__error);
        }
        return execResult;
      }
    }

    case 'click': {
      const { selector, tabId } = params;
      if (!selector) throw new Error('Missing "selector" parameter');
      const targetId = await resolveTabId(tabId);

      const results = await chrome.scripting.executeScript({
        target: { tabId: targetId },
        func: (sel) => {
          const el = document.querySelector(sel);
          if (!el) return { found: false };
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.click();
          return { found: true, tagName: el.tagName, text: el.innerText };
        },
        args: [selector]
      });

      const res = results[0]?.result;
      if (!res?.found) {
        throw new Error(`Element matching "${selector}" not found on page`);
      }
      return res;
    }

    case 'type': {
      const { selector, text, clear = true, pressEnter = false, tabId } = params;
      if (!selector) throw new Error('Missing "selector" parameter');
      if (text === undefined) throw new Error('Missing "text" parameter');
      const targetId = await resolveTabId(tabId);

      const results = await chrome.scripting.executeScript({
        target: { tabId: targetId },
        func: (sel, val, doClear, doEnter) => {
          const el = document.querySelector(sel);
          if (!el) return { found: false };

          el.focus();
          if (doClear) {
            el.value = '';
          }
          el.value += val;

          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));

          if (doEnter) {
            const enterEvent = new KeyboardEvent('keydown', {
              key: 'Enter',
              code: 'Enter',
              keyCode: 13,
              which: 13,
              bubbles: true
            });
            el.dispatchEvent(enterEvent);
            if (el.form) {
              el.form.requestSubmit ? el.form.requestSubmit() : el.form.submit();
            }
          }

          return { found: true, currentValue: el.value };
        },
        args: [selector, text, clear, pressEnter]
      });

      const res = results[0]?.result;
      if (!res?.found) {
        throw new Error(`Input matching "${selector}" not found`);
      }
      return res;
    }

    case 'get_page_content': {
      const targetId = await resolveTabId(params.tabId);
      const results = await chrome.scripting.executeScript({
        target: { tabId: targetId },
        func: () => {
          return {
            title: document.title,
            url: window.location.href,
            heading: document.querySelector('h1, h2')?.innerText || '',
            bodyText: document.body.innerText.slice(0, 5000),
            inputCount: document.querySelectorAll('input, textarea, button').length
          };
        }
      });
      return results[0]?.result;
    }

    case 'scroll': {
      const { x = 0, y = 500, tabId } = params;
      const targetId = await resolveTabId(tabId);
      await chrome.scripting.executeScript({
        target: { tabId: targetId },
        func: (sx, sy) => window.scrollBy({ left: sx, top: sy, behavior: 'smooth' }),
        args: [x, y]
      });
      return { scrolled: { x, y } };
    }

    default:
      throw new Error(`Unknown action: ${action}`);
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'RECONNECT') {
    if (nativePort) {
      try { nativePort.disconnect(); } catch {}
      nativePort = null;
    }
    connectNative();
    sendResponse({ status: 'connecting' });
  } else if (message.type === 'GET_STATUS') {
    (async () => {
      const isConnected = nativePort !== null;
      const { activityLogs = [] } = await chrome.storage.local.get('activityLogs');
      let activeTabInfo = null;
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab) {
          activeTabInfo = {
            id: tab.id,
            title: tab.title || 'Untitled',
            url: tab.url || '',
            favIconUrl: tab.favIconUrl || ''
          };
        }
      } catch {}
      sendResponse({ isConnected, activityLogs, activeTab: activeTabInfo, transport: 'Native Messaging' });
    })();
    return true;
  }
});

connectNative();
