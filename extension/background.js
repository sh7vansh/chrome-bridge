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

    await logActivity(logMsg, logType);

    try {
      const result = await handleAction(action, params);
      if (id && nativePort) {
        nativePort.postMessage({ id, success: true, result });
      }
    } catch (err) {
      console.error(`[NativeBridge] Action ${action} failed:`, err);
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

async function resolveTabId(specifiedId) {
  if (specifiedId) return specifiedId;
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (activeTab) return activeTab.id;
  const [anyTab] = await chrome.tabs.query({ active: true });
  if (anyTab) return anyTab.id;
  throw new Error('No active browser tab found');
}

// In-page automation engine injected via chrome.scripting.executeScript
function inPageDOMOperation(payload) {
  const { operation, args } = payload;

  const INTERACTIVE_ROLES = new Set([
    'button', 'link', 'checkbox', 'radio', 'combobox', 'textbox',
    'searchbox', 'menuitem', 'menuitemcheckbox', 'menuitemradio',
    'tab', 'switch', 'slider', 'spinbutton', 'treeitem', 'option'
  ]);

  const IGNORED_TAGS = new Set([
    'SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'SVG', 'CANVAS',
    'META', 'LINK', 'HEAD', 'IFRAME', 'EMBED', 'OBJECT'
  ]);

  function isVisible(el, style) {
    if (el.hasAttribute('hidden')) return false;
    if (el.getAttribute('aria-hidden') === 'true') return false;
    if (el.hasAttribute('inert')) return false;

    // Use native checkVisibility when available
    if (typeof el.checkVisibility === 'function') {
      if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) {
        if (el.tagName === 'INPUT' && (el.type === 'checkbox' || el.type === 'radio')) {
          return true;
        }
        return false;
      }
    }

    if (!style) style = window.getComputedStyle(el);
    if (style.display === 'none') return false;
    if (style.visibility === 'hidden' || style.visibility === 'collapse') return false;
    if (parseFloat(style.opacity) < 0.05) return false;

    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
      if (el.tagName === 'INPUT' && (el.type === 'checkbox' || el.type === 'radio')) {
        return true;
      }
      return false;
    }
    return true;
  }

  function getAccessibleName(el) {
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const parts = labelledby.split(/\s+/).map(id => document.getElementById(id)?.innerText?.trim()).filter(Boolean);
      if (parts.length > 0) return parts.join(' ');
    }

    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();

    if (el.id && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')) {
      const labelEl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (labelEl && labelEl.innerText.trim()) return labelEl.innerText.trim();
    }
    const parentLabel = el.closest('label');
    if (parentLabel && parentLabel.innerText.trim()) {
      return parentLabel.innerText.trim();
    }

    if (el.getAttribute('placeholder')) return el.getAttribute('placeholder').trim();
    if (el.getAttribute('title')) return el.getAttribute('title').trim();
    if (el.getAttribute('alt')) return el.getAttribute('alt').trim();

    const directText = Array.from(el.childNodes)
      .filter(node => node.nodeType === Node.TEXT_NODE)
      .map(node => node.textContent.trim())
      .filter(Boolean)
      .join(' ');
    if (directText) return directText.slice(0, 120);

    if (['BUTTON', 'A', 'SUMMARY', 'OPTION'].includes(el.tagName)) {
      const fullText = el.innerText?.trim();
      if (fullText) return fullText.slice(0, 120);
    }

    return '';
  }

  function getComputedRole(el) {
    const explicitRole = el.getAttribute('role');
    if (explicitRole) return explicitRole.toLowerCase().trim();

    const tag = el.tagName.toLowerCase();
    switch (tag) {
      case 'a': return el.hasAttribute('href') ? 'link' : 'generic';
      case 'button': return 'button';
      case 'input': {
        const type = (el.getAttribute('type') || 'text').toLowerCase();
        if (['button', 'submit', 'reset', 'image'].includes(type)) return 'button';
        if (type === 'checkbox') return 'checkbox';
        if (type === 'radio') return 'radio';
        if (type === 'search') return 'searchbox';
        return 'textbox';
      }
      case 'select': return 'combobox';
      case 'textarea': return 'textbox';
      case 'summary': return 'button';
      case 'details': return 'group';
      case 'h1': return 'heading[level=1]';
      case 'h2': return 'heading[level=2]';
      case 'h3': return 'heading[level=3]';
      case 'h4': return 'heading[level=4]';
      case 'h5': return 'heading[level=5]';
      case 'h6': return 'heading[level=6]';
      case 'nav': return 'navigation';
      case 'main': return 'main';
      case 'header': return 'banner';
      case 'footer': return 'contentinfo';
      case 'form': return 'form';
      case 'table': return 'table';
      default: return 'generic';
    }
  }

  function isActionable(el, role, style) {
    if (['A', 'BUTTON', 'SELECT', 'TEXTAREA', 'DETAILS', 'SUMMARY'].includes(el.tagName)) {
      if (el.tagName === 'A' && !el.hasAttribute('href')) return false;
      return true;
    }

    if (el.tagName === 'INPUT') {
      return (el.getAttribute('type') || 'text').toLowerCase() !== 'hidden';
    }

    if (INTERACTIVE_ROLES.has(role)) return true;
    if (el.tabIndex >= 0 && el.tagName !== 'IFRAME') return true;
    if (el.isContentEditable) return true;
    if (style.cursor === 'pointer' && el.children.length === 0) return true;

    return false;
  }

  function generateSnapshot() {
    const root = document.body;
    if (!root) return { snapshot: 'Empty Page', totalInteractive: 0, epoch: Date.now() };

    const refMap = new Map();
    const refsMapObj = {};
    const elementWeakMap = new WeakMap();
    const historyMap = window.__chrome_bridge_history || {};
    let refCounter = 1;
    const lines = [];

    const viewportHeight = window.innerHeight;
    const viewportWidth = window.innerWidth;

    // Use DOM TreeWalker for high-performance pre-order traversal
    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_ELEMENT,
      {
        acceptNode: (node) => {
          if (IGNORED_TAGS.has(node.tagName)) return NodeFilter.FILTER_REJECT;
          if (node.hasAttribute('hidden') || node.getAttribute('aria-hidden') === 'true' || node.hasAttribute('inert')) {
            return NodeFilter.FILTER_REJECT;
          }
          const style = window.getComputedStyle(node);
          if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) < 0.05) {
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );

    function getNodeDepth(node) {
      let d = 0;
      let cur = node;
      while (cur && cur !== root) {
        d++;
        cur = cur.parentElement;
      }
      return d;
    }

    let currentNode = walker.currentNode;
    while (currentNode) {
      if (currentNode !== root) {
        const node = currentNode;
        const style = window.getComputedStyle(node);
        if (isVisible(node, style)) {
          const role = getComputedRole(node);
          const actionable = isActionable(node, role, style);
          const name = getAccessibleName(node);
          const depth = Math.min(6, getNodeDepth(node));
          const indent = '  '.repeat(depth);

          if (actionable) {
            const refId = refCounter++;
            refMap.set(refId, node);
            if (typeof WeakRef !== 'undefined') {
              refsMapObj[refId] = new WeakRef(node);
            } else {
              refsMapObj[refId] = node;
            }
            elementWeakMap.set(node, refId);

            // Accumulate in history map
            historyMap[refId] = {
              ref: `#${refId}`,
              tag: node.tagName.toLowerCase(),
              role: role,
              name: name,
              className: node.className || '',
            };

            const extras = [];
            if (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA') {
              if (node.value) extras.push(`value="${node.value.slice(0, 50)}"`);
              if (node.placeholder && node.placeholder !== name) extras.push(`placeholder="${node.placeholder}"`);
            }
            if (node.checked) extras.push('checked');
            if (node.disabled || node.getAttribute('aria-disabled') === 'true') extras.push('disabled');
            if (node.hasAttribute('aria-expanded')) extras.push(`expanded=${node.getAttribute('aria-expanded')}`);
            if (node.hasAttribute('aria-selected')) extras.push(`selected=${node.getAttribute('aria-selected')}`);
            if (node.tagName === 'A' && node.getAttribute('href')) {
              const href = node.getAttribute('href');
              if (href && !href.startsWith('javascript:')) extras.push(`href="${href.slice(0, 80)}"`);
            }

            const rect = node.getBoundingClientRect();
            const inViewport = (rect.top < viewportHeight && rect.bottom > 0 && rect.left < viewportWidth && rect.right > 0);
            if (!inViewport) extras.push('offscreen');

            const extraStr = extras.length > 0 ? ` (${extras.join(', ')})` : '';
            const nameStr = name ? ` "${name}"` : '';
            lines.push(`${indent}- ${role} [#${refId}]${nameStr}${extraStr}`);
          } else if (role !== 'generic' || (name && name.length > 0 && node.children.length === 0)) {
            const nameStr = name ? `: "${name}"` : '';
            lines.push(`${indent}- ${role}${nameStr}`);
          }
        }
      }
      currentNode = walker.nextNode();
    }

    const epoch = Date.now();
    window.__AG_REGISTRY__ = {
      epoch,
      refMap,
      elementWeakMap,
      totalInteractive: refCounter - 1
    };
    window.__chrome_bridge_refs = refsMapObj;
    window.__chrome_bridge_history = historyMap;

    return {
      snapshot: [`PAGE: "${document.title}" (${window.location.href})`, ...lines].join('\n'),
      totalInteractive: refCounter - 1,
      epoch,
      title: document.title,
      url: window.location.href
    };
  }

  function resolveTarget(target) {
    if (!target) return null;

    let refId = null;
    let selector = null;

    if (typeof target === 'number') {
      refId = target;
    } else if (typeof target === 'string') {
      const str = target.trim();
      const mBracket = str.match(/^\[#\s*(\d+)\]$/);
      const mHash = str.match(/^#(\d+)$/);
      const mRef = str.match(/^ref[:=](\d+)$/i);
      if (mBracket) refId = parseInt(mBracket[1], 10);
      else if (mHash) refId = parseInt(mHash[1], 10);
      else if (mRef) refId = parseInt(mRef[1], 10);
      else selector = str;
    } else if (typeof target === 'object') {
      if (target.type === 'ref' || target.refId !== undefined) {
        refId = parseInt(target.refId, 10);
      } else if (target.type === 'css' || target.selector) {
        selector = target.selector;
      }
    }

    if (refId !== null) {
      let el = window.__AG_REGISTRY__?.refMap?.get(refId);
      if (!el && window.__chrome_bridge_refs?.[refId]) {
        const refEntry = window.__chrome_bridge_refs[refId];
        el = refEntry && typeof refEntry.deref === 'function' ? refEntry.deref() : refEntry;
      }

      if (el && el.isConnected) {
        return { el, targetLabel: `[#${refId}]` };
      }

      // Check historical snapshot and compute suggestions
      const hist = window.__chrome_bridge_history?.[refId];
      const suggestions = [];
      if (window.__AG_REGISTRY__?.refMap) {
        for (const [candRef, candEl] of window.__AG_REGISTRY__.refMap.entries()) {
          if (!candEl.isConnected) continue;
          const candRole = getComputedRole(candEl);
          const candName = getAccessibleName(candEl);
          if (hist && (candRole === hist.role || (candName && hist.name && candName.toLowerCase().includes(hist.name.toLowerCase())))) {
            suggestions.push({ ref: `#${candRef}`, role: candRole, name: candName });
            if (suggestions.length >= 3) break;
          }
        }
      }

      return {
        error: {
          code: 'ELEMENT_NOT_FOUND',
          target: `[#${refId}]`,
          stale: true,
          suggestions,
          url: window.location.href
        }
      };
    }

    if (selector) {
      const el = document.querySelector(selector);
      if (el) {
        return { el, targetLabel: selector };
      }
      return {
        error: {
          code: 'ELEMENT_NOT_FOUND',
          target: selector,
          stale: false,
          suggestions: [],
          url: window.location.href
        }
      };
    }

    return { error: { code: 'ELEMENT_NOT_FOUND', target: String(target), suggestions: [] } };
  }

  function introspectDOMState(target) {
    const res = resolveTarget(target);
    if (!res || res.error || !res.el) {
      return { present: false, domState: 'absent from DOM' };
    }
    const el = res.el;
    const style = window.getComputedStyle(el);
    if (style.display === 'none') {
      return { present: true, domState: 'hidden in DOM (display: none)' };
    }
    if (style.visibility === 'hidden') {
      return { present: true, domState: 'hidden in DOM (visibility: hidden)' };
    }
    if (parseFloat(style.opacity) < 0.05) {
      return { present: true, domState: 'hidden in DOM (opacity < 0.05)' };
    }
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
      return { present: true, domState: 'zero dimensions' };
    }
    return { present: true, domState: 'visible in DOM' };
  }

  switch (operation) {
    case 'snapshot':
      return generateSnapshot();

    case 'introspect_timeout': {
      const intro = introspectDOMState(args.target);
      return {
        readyState: document.readyState,
        url: window.location.href,
        domState: intro.domState,
        present: intro.present
      };
    }

    case 'click': {
      const { target, button = 'left', count = 1 } = args;
      const res = resolveTarget(target);
      if (res.error) return { __error: res.error };

      const el = res.el;
      el.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });

      // Hit-test inspection
      const rect = el.getBoundingClientRect();
      const cx = Math.max(0, Math.min(window.innerWidth - 1, rect.left + rect.width / 2));
      const cy = Math.max(0, Math.min(window.innerHeight - 1, rect.top + rect.height / 2));
      const hit = document.elementFromPoint(cx, cy);

      if (hit && hit !== el && !el.contains(hit) && !hit.contains(el)) {
        const interceptor = hit.closest('dialog, [role="dialog"], header, .modal, .overlay, [aria-modal="true"]') || hit;
        const interceptorRef = window.__AG_REGISTRY__?.elementWeakMap?.get(interceptor);
        return {
          __error: {
            code: 'ACTION_INTERCEPTED',
            target: res.targetLabel,
            interceptorTag: interceptor.tagName.toLowerCase(),
            interceptorRef: interceptorRef ? `#${interceptorRef}` : null,
            interceptorDesc: interceptor.innerText?.slice(0, 50) || interceptor.className || ''
          }
        };
      }

      el.focus();
      for (let i = 0; i < count; i++) {
        el.click();
      }
      return { status: 'ok', action: 'click', target: res.targetLabel, tagName: el.tagName, text: el.innerText };
    }

    case 'type': {
      const { target, text, clear = true, pressEnter = false } = args;
      const res = resolveTarget(target);
      if (res.error) return { __error: res.error };

      const el = res.el;
      el.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });
      el.focus();

      if (clear) {
        if ('value' in el) el.value = '';
        else if (el.isContentEditable) el.innerText = '';
      }

      if ('value' in el) {
        el.value += text;
      } else if (el.isContentEditable) {
        el.innerText += text;
      }

      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));

      if (pressEnter) {
        const enterDown = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true });
        el.dispatchEvent(enterDown);
        if (el.form) {
          el.form.requestSubmit ? el.form.requestSubmit() : el.form.submit();
        }
      }

      return { status: 'ok', action: 'type', target: res.targetLabel, currentValue: el.value || el.innerText };
    }

    case 'hover': {
      const res = resolveTarget(args.target);
      if (res.error) return { __error: res.error };
      const el = res.el;
      el.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });
      el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
      el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
      el.dispatchEvent(new MouseEvent('mousemove', { bubbles: true }));
      return { status: 'ok', action: 'hover', target: res.targetLabel };
    }

    case 'scroll': {
      const { x = 0, y = 500, target } = args;
      if (target) {
        const res = resolveTarget(target);
        if (res.error) return { __error: res.error };
        res.el.scrollBy({ left: x, top: y, behavior: 'smooth' });
        return { scrolled: { x, y }, target: res.targetLabel };
      }
      window.scrollBy({ left: x, top: y, behavior: 'smooth' });
      return { scrolled: { x, y } };
    }

    case 'select_option': {
      const { target, value } = args;
      const res = resolveTarget(target);
      if (res.error) return { __error: res.error };
      const el = res.el;
      if (el.tagName !== 'SELECT') {
        return { __error: { code: 'ELEMENT_NOT_FOUND', target: res.targetLabel, message: `Element is not a <select> dropdown` } };
      }
      let found = false;
      for (const opt of el.options) {
        if (opt.value === value || opt.text === value) {
          opt.selected = true;
          found = true;
          break;
        }
      }
      if (found) {
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return { status: 'ok', action: 'select', value, target: res.targetLabel };
      }
      return { __error: { code: 'ELEMENT_NOT_FOUND', target: res.targetLabel, message: `Option "${value}" not found in select` } };
    }

    case 'get_text': {
      const res = resolveTarget(args.target);
      if (res.error) return { __error: res.error };
      return { text: res.el.innerText || res.el.textContent || '' };
    }

    case 'get_attribute': {
      const { target, name } = args;
      const res = resolveTarget(target);
      if (res.error) return { __error: res.error };
      return { value: res.el.getAttribute(name) };
    }

    case 'press_key': {
      const { key } = args;
      const targetEl = document.activeElement || document.body;
      const evtDown = new KeyboardEvent('keydown', { key, bubbles: true });
      const evtUp = new KeyboardEvent('keyup', { key, bubbles: true });
      targetEl.dispatchEvent(evtDown);
      targetEl.dispatchEvent(evtUp);
      return { status: 'ok', key };
    }

    case 'wait_for': {
      const { target, state = 'visible' } = args;
      const res = resolveTarget(target);
      if (state === 'attached') {
        const attached = !res.error && res.el && res.el.isConnected;
        return { matched: attached };
      }
      if (state === 'hidden') {
        const hidden = res.error || !res.el || !isVisible(res.el);
        return { matched: hidden };
      }
      // visible
      const visible = !res.error && res.el && isVisible(res.el);
      return { matched: visible };
    }

    case 'wait_for_url': {
      const { pattern } = args;
      const regex = new RegExp(pattern);
      return { matched: regex.test(window.location.href), currentUrl: window.location.href };
    }

    default:
      return { __error: { message: `Unknown inPage operation: ${operation}` } };
  }
}

async function executeInPage(tabId, operation, args = {}) {
  const targetId = await resolveTabId(tabId);
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
      return tab ? { id: tab.id, url: tab.url, title: tab.title, favIconUrl: tab.favIconUrl, active: true } : null;
    }

    case 'get_tab': {
      const targetId = await resolveTabId(params.tabId);
      const tab = await chrome.tabs.get(targetId);
      return tab ? { id: tab.id, url: tab.url, title: tab.title, favIconUrl: tab.favIconUrl, active: tab.active } : null;
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

    case 'wait_for': {
      const targetId = await resolveTabId(params.tabId);
      const timeout = params.timeout || 10.0;
      const startTime = Date.now();
      while (Date.now() - startTime < timeout * 1000) {
        try {
          const res = await executeInPage(targetId, 'wait_for', { target: params.target, state: params.state });
          if (res.matched) return true;
        } catch {}
        await new Promise(r => setTimeout(r, 200));
      }
      
      // Introspect DOM state for rich error diagnostics
      let readyState = 'unknown';
      let domState = 'unknown';
      let url = '';
      try {
        const intro = await executeInPage(targetId, 'introspect_timeout', { target: params.target });
        readyState = intro.readyState || readyState;
        domState = intro.domState || domState;
        url = intro.url || url;
      } catch {}

      const err = new Error(`Timed out waiting for element`);
      err.structuredError = {
        code: 'TIMEOUT',
        target: String(params.target),
        timeout,
        tabId: targetId,
        url,
        readyState,
        domState
      };
      throw err;
    }

    case 'wait_for_url': {
      const targetId = await resolveTabId(params.tabId);
      const timeout = params.timeout || 15.0;
      const startTime = Date.now();
      while (Date.now() - startTime < timeout * 1000) {
        try {
          const res = await executeInPage(targetId, 'wait_for_url', { pattern: params.pattern });
          if (res.matched) return true;
        } catch {}
        await new Promise(r => setTimeout(r, 200));
      }
      const err = new Error(`Timed out waiting for URL pattern`);
      err.structuredError = {
        code: 'TIMEOUT',
        target: params.pattern,
        timeout,
        tabId: targetId
      };
      throw err;
    }

    case 'execute_script': {
      const { code, tabId } = params;
      if (!code) throw new Error('Missing "code" parameter');
      const targetId = await resolveTabId(tabId);

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
