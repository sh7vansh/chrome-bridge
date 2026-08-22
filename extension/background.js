import { inPageDOMOperation } from './dom-engine.js';

const HOST_NAME = 'com.chrome_bridge.native';
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

async function logActivity(message, type = 'info', details = null) {
  const { activityLogs = [] } = await chrome.storage.local.get('activityLogs');
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const newLog = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    timestamp: timeStr,
    message,
    type,
    details: details ? (typeof details === 'object' ? JSON.stringify(details, null, 2) : String(details)) : null
  };
  const updatedLogs = [newLog, ...activityLogs].slice(0, 80);
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
      const tgt = params.target?.refId ? `[#${params.target.refId}]` : (params.target?.selector || params.selector || '');
      logMsg = `Clicked "${tgt}"`;
      logType = 'click';
    } else if (action === 'type') {
      const tgt = params.target?.refId ? `[#${params.target.refId}]` : (params.target?.selector || params.selector || '');
      logMsg = `Typed "${params.text?.slice(0, 25)}" into ${tgt}`;
      logType = 'type';
    } else if (action === 'screenshot') {
      logMsg = 'Captured visible tab screenshot';
      logType = 'screenshot';
    } else if (action === 'get_page_content') {
      logMsg = 'Generated Semantic DOM Snapshot';
      logType = 'content';
    } else if (action === 'execute_script') {
      logMsg = `Evaluated JS: ${params.code?.slice(0, 35)}...`;
      logType = 'eval';
    } else if (action === 'list_tabs') {
      logMsg = 'Listed open tabs';
      logType = 'tabs';
    } else if (action === 'get_active_tab' || action === 'get_tab') {
      logMsg = 'Queried tab details';
      logType = 'tabs';
    } else if (action === 'scroll') {
      logMsg = `Scrolled page (${params.x || 0}, ${params.y || 500})`;
      logType = 'scroll';
    }

    await logActivity(logMsg, logType, params);

    try {
      const result = await handleAction(action, params);
      if (id && nativePort) {
        nativePort.postMessage({ id, success: true, result });
      }
    } catch (err) {
      console.error(`[NativeBridge] Action ${action} failed:`, err);
      await logActivity(`Failed ${action}: ${err.message}`, 'error', err.structuredError || err.message);
      if (id && nativePort) {
        nativePort.postMessage({ id, success: false, error: err.structuredError || err.message });
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

export const TabExecutionCoordinator = {
  async resolveTabId(specifiedId) {
    if (specifiedId) return specifiedId;
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (activeTab) return activeTab.id;
    const [anyTab] = await chrome.tabs.query({ active: true });
    if (anyTab) return anyTab.id;
    throw new Error('No active browser tab found');
  },

  async executeInPage(tabId, operation, args = {}) {
    const targetId = await this.resolveTabId(tabId);
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: targetId },
        func: inPageDOMOperation,
        args: [{ operation, args }]
      });

      const res = results[0]?.result;
      if (res && res.__error) {
        const customErr = new Error(res.__error.message || `Action error: ${res.__error.code}`);
        customErr.structuredError = res.__error;
        throw customErr;
      }
      return res;
    } catch (err) {
      if (err.structuredError) throw err;
      const errMsg = err.message || '';
      // If context was detached during an async wait due to a hard page navigation, retry after tab loads
      if (errMsg.includes('frame was detached') || errMsg.includes('Cannot access contents of url') || errMsg.includes('tab was closed')) {
        if (operation === 'wait_for' || operation === 'wait_for_url') {
          await new Promise(r => setTimeout(r, 400));
          const tab = await chrome.tabs.get(targetId).catch(() => null);
          if (tab && tab.status === 'complete') {
            const retryResults = await chrome.scripting.executeScript({
              target: { tabId: targetId },
              func: inPageDOMOperation,
              args: [{ operation, args }]
            });
            const retryRes = retryResults[0]?.result;
            if (retryRes && retryRes.__error) {
              const customErr = new Error(retryRes.__error.message || `Action error: ${retryRes.__error.code}`);
              customErr.structuredError = retryRes.__error;
              throw customErr;
            }
            return retryRes;
          }
        }
      }
      throw err;
    }
  },

  async evaluateScript(tabId, code) {
    if (!code) throw new Error('Missing "code" parameter');
    const targetId = await this.resolveTabId(tabId);
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

      const results = await chrome.scripting.executeScript({
        target: { tabId: targetId },
        world: 'MAIN',
        func: async (expression) => {
          if (expression === 'document.title') return document.title;
          if (expression === 'location.href' || expression === 'window.location.href') return window.location.href;
          try {
            return await (0, eval)(expression);
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
};

const resolveTabId = (id) => TabExecutionCoordinator.resolveTabId(id);
const executeInPage = (id, op, args) => TabExecutionCoordinator.executeInPage(id, op, args);

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
      return tab ? { id: tab.id, url: tab.url, title: tab.title, favIconUrl: tab.favIconUrl, active: true } : null;
    }

    case 'get_tab': {
      const targetId = await resolveTabId(params.tabId);
      const tab = await chrome.tabs.get(targetId);
      return tab ? { id: tab.id, url: tab.url, title: tab.title, favIconUrl: tab.favIconUrl, active: tab.active } : null;
    }

    case 'new_tab':
    case 'navigate': {
      const { url = 'about:blank', tabId, newTab = (action === 'new_tab') } = params;
      if (!url && action === 'navigate') throw new Error('Missing "url" parameter');
      if (newTab || action === 'new_tab') {
        const created = await chrome.tabs.create({ url: url || 'about:blank', active: true });
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

    case 'reload': {
      const targetId = await resolveTabId(params.tabId);
      await chrome.tabs.reload(targetId, { bypassCache: !!params.bypassCache });
      return { success: true, tabId: targetId };
    }

    case 'go_back': {
      const targetId = await resolveTabId(params.tabId);
      await chrome.tabs.goBack(targetId);
      return { success: true, tabId: targetId };
    }

    case 'go_forward': {
      const targetId = await resolveTabId(params.tabId);
      await chrome.tabs.goForward(targetId);
      return { success: true, tabId: targetId };
    }

    case 'screenshot': {
      const targetId = await resolveTabId(params.tabId);
      const tab = await chrome.tabs.get(targetId);
      const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
      return { dataUrl };
    }

    case 'get_page_content': {
      const targetId = await resolveTabId(params.tabId);
      return await executeInPage(targetId, 'snapshot', params);
    }

    case 'click': {
      const targetId = await resolveTabId(params.tabId);
      const target = params.target || params.selector;
      return await executeInPage(targetId, 'click', { target, button: params.button, count: params.count });
    }

    case 'type': {
      const targetId = await resolveTabId(params.tabId);
      const target = params.target || params.selector;
      return await executeInPage(targetId, 'type', {
        target,
        text: params.text,
        clear: params.clear !== false,
        pressEnter: !!params.pressEnter
      });
    }

    case 'hover': {
      const targetId = await resolveTabId(params.tabId);
      return await executeInPage(targetId, 'hover', { target: params.target || params.selector });
    }

    case 'scroll': {
      const targetId = await resolveTabId(params.tabId);
      return await executeInPage(targetId, 'scroll', {
        x: params.x,
        y: params.y,
        target: params.target || params.selector
      });
    }

    case 'select_option': {
      const targetId = await resolveTabId(params.tabId);
      return await executeInPage(targetId, 'select_option', {
        target: params.target || params.selector,
        value: params.value
      });
    }

    case 'get_text': {
      const targetId = await resolveTabId(params.tabId);
      return await executeInPage(targetId, 'get_text', { target: params.target || params.selector });
    }

    case 'get_attribute': {
      const targetId = await resolveTabId(params.tabId);
      return await executeInPage(targetId, 'get_attribute', {
        target: params.target || params.selector,
        name: params.name
      });
    }

    case 'press_key': {
      const targetId = await resolveTabId(params.tabId);
      return await executeInPage(targetId, 'press_key', { key: params.key });
    }

    case 'find_element': {
      const targetId = await resolveTabId(params.tabId);
      return await executeInPage(targetId, 'find_element', params);
    }

    case 'query_elements': {
      const targetId = await resolveTabId(params.tabId);
      return await executeInPage(targetId, 'query_elements', params);
    }

    case 'fill_form': {
      const targetId = await resolveTabId(params.tabId);
      return await executeInPage(targetId, 'fill_form', params);
    }

    case 'extract_items': {
      const targetId = await resolveTabId(params.tabId);
      return await executeInPage(targetId, 'extract_items', params);
    }

    case 'wait_for': {
      const targetId = await resolveTabId(params.tabId);
      const res = await executeInPage(targetId, 'wait_for', {
        target: params.target || params.selector,
        state: params.state || 'visible',
        timeout: params.timeout || 10.0
      });
      return res?.matched !== false;
    }

    case 'wait_for_url': {
      const targetId = await resolveTabId(params.tabId);
      const res = await executeInPage(targetId, 'wait_for_url', {
        pattern: params.pattern,
        timeout: params.timeout || 15.0
      });
      return res?.matched !== false;
    }

    case 'execute_script': {
      return await TabExecutionCoordinator.evaluateScript(params.tabId, params.code);
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
      sendResponse({
        isConnected,
        activityLogs,
        activeTab: activeTabInfo,
        transport: 'Native Messaging (com.chrome_bridge.native)',
        hostName: HOST_NAME
      });
    })();
    return true;
  } else if (message.type === 'HIGHLIGHT_REFS') {
    (async () => {
      try {
        const tabId = await resolveTabId(message.tabId);
        const result = await executeInPage(tabId, 'highlight_refs');
        sendResponse({ success: true, ...result });
      } catch (err) {
        sendResponse({ success: false, error: err.message });
      }
    })();
    return true;
  } else if (message.type === 'GET_PAGE_METRICS') {
    (async () => {
      try {
        const tabId = await resolveTabId(message.tabId);
        const result = await executeInPage(tabId, 'get_metrics');
        sendResponse({ success: true, metrics: result });
      } catch (err) {
        sendResponse({ success: false, error: err.message });
      }
    })();
    return true;
  } else if (message.type === 'CAPTURE_SNAPSHOT') {
    (async () => {
      try {
        const tabId = await resolveTabId(message.tabId);
        const result = await executeInPage(tabId, 'snapshot');
        sendResponse({ success: true, snapshot: result.snapshot, totalInteractive: result.totalInteractive });
      } catch (err) {
        sendResponse({ success: false, error: err.message });
      }
    })();
    return true;
  } else if (message.type === 'PING') {
    sendResponse({ pong: true, timestamp: Date.now() });
    return false;
  }
});

connectNative();
