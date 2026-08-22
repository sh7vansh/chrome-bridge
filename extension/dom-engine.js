/**
 * In-Page DOM Automation Engine for Chrome Bridge
 * 
 * Provides isolated DOM traversal, Semantic DOM Snapshot generation,
 * Element Ref-ID indexing, fuzzy locator matching, and hit-testing verification.
 */

export async function inPageDOMOperation(payload) {
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

  function waitForCondition(target, state = 'visible', timeout = 10.0) {
    return new Promise((resolve) => {
      const timeoutMs = (timeout || 10.0) * 1000;
      const startTime = performance.now();

      function checkCondition() {
        const res = resolveTarget(target);
        if (state === 'attached') {
          return !res.error && res.el && res.el.isConnected;
        }
        if (state === 'hidden') {
          return res.error || !res.el || !isVisible(res.el);
        }
        // default 'visible'
        return !res.error && res.el && isVisible(res.el);
      }

      // Fast-path check
      if (checkCondition()) {
        return resolve({ matched: true, elapsed: performance.now() - startTime });
      }

      let resolved = false;
      let observer = null;
      let timer = null;

      function cleanup() {
        if (observer) {
          try { observer.disconnect(); } catch {}
          observer = null;
        }
        if (timer) {
          clearTimeout(timer);
          timer = null;
        }
        window.removeEventListener('transitionend', onActivity);
        window.removeEventListener('animationend', onActivity);
        window.removeEventListener('popstate', onActivity);
        window.removeEventListener('hashchange', onActivity);
      }

      function onActivity() {
        if (resolved) return;
        if (checkCondition()) {
          resolved = true;
          cleanup();
          resolve({ matched: true, elapsed: performance.now() - startTime });
        }
      }

      timer = setTimeout(() => {
        if (resolved) return;
        resolved = true;
        cleanup();

        const intro = introspectDOMState(target);
        let autoSnapshot = '';
        try {
          const snapRes = generateSnapshot();
          autoSnapshot = snapRes.snapshot || '';
        } catch {}

        let targetLabel = String(target);
        if (typeof target === 'object' && target !== null) {
          if (target.refId !== undefined) targetLabel = `[#${target.refId}]`;
          else if (target.selector) targetLabel = target.selector;
        }

        resolve({
          __error: {
            code: 'TIMEOUT',
            target: targetLabel,
            timeout,
            readyState: document.readyState,
            domState: intro.domState,
            url: window.location.href,
            auto_snapshot: autoSnapshot
          }
        });
      }, timeoutMs);

      try {
        observer = new MutationObserver(() => {
          onActivity();
        });
        const targetNode = document.documentElement || document.body;
        if (targetNode) {
          observer.observe(targetNode, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['style', 'class', 'hidden', 'aria-hidden', 'inert', 'disabled']
          });
        }
      } catch {}

      window.addEventListener('transitionend', onActivity);
      window.addEventListener('animationend', onActivity);
      window.addEventListener('popstate', onActivity);
      window.addEventListener('hashchange', onActivity);

      // Micro-interval fallback for complex off-DOM transitions
      const interval = setInterval(() => {
        if (resolved) {
          clearInterval(interval);
          return;
        }
        onActivity();
      }, 250);
    });
  }

  function waitForUrl(pattern, timeout = 15.0) {
    return new Promise((resolve) => {
      const timeoutMs = (timeout || 15.0) * 1000;
      const startTime = performance.now();
      const regex = new RegExp(pattern);

      function checkUrl() {
        return regex.test(window.location.href);
      }

      if (checkUrl()) {
        return resolve({ matched: true, currentUrl: window.location.href, elapsed: performance.now() - startTime });
      }

      let resolved = false;
      let timer = null;
      let observer = null;

      function cleanup() {
        if (timer) {
          clearTimeout(timer);
          timer = null;
        }
        if (observer) {
          try { observer.disconnect(); } catch {}
          observer = null;
        }
        window.removeEventListener('popstate', onUrlEvent);
        window.removeEventListener('hashchange', onUrlEvent);
      }

      function onUrlEvent() {
        if (resolved) return;
        if (checkUrl()) {
          resolved = true;
          cleanup();
          resolve({ matched: true, currentUrl: window.location.href, elapsed: performance.now() - startTime });
        }
      }

      timer = setTimeout(() => {
        if (resolved) return;
        resolved = true;
        cleanup();

        let autoSnapshot = '';
        try {
          const snapRes = generateSnapshot();
          autoSnapshot = snapRes.snapshot || '';
        } catch {}

        resolve({
          __error: {
            code: 'TIMEOUT',
            target: pattern,
            timeout,
            readyState: document.readyState,
            domState: `URL is '${window.location.href}' (did not match pattern '${pattern}')`,
            url: window.location.href,
            auto_snapshot: autoSnapshot
          }
        });
      }, timeoutMs);

      window.addEventListener('popstate', onUrlEvent);
      window.addEventListener('hashchange', onUrlEvent);

      try {
        observer = new MutationObserver(() => {
          onUrlEvent();
        });
        const targetNode = document.documentElement || document.body;
        if (targetNode) {
          observer.observe(targetNode, { childList: true, subtree: false });
        }
      } catch {}
    });
  }

  function tagElement(el) {
    if (!el) return null;
    if (!window.__cb_handle_counter) window.__cb_handle_counter = 0;
    let bridgeId = el.getAttribute('data-cbridge-id');
    if (!bridgeId) {
      bridgeId = 'cb_' + (++window.__cb_handle_counter) + '_' + Date.now().toString(36);
      el.setAttribute('data-cbridge-id', bridgeId);
    }
    const text = getAccessibleName(el);
    const role = getComputedRole(el);
    return {
      selector: '[data-cbridge-id="' + bridgeId + '"]',
      tagName: el.tagName.toLowerCase(),
      role: role,
      text: text.slice(0, 100),
      id: el.id || '',
      name: el.getAttribute('name') || '',
      placeholder: el.getAttribute('placeholder') || '',
      value: el.value || ''
    };
  }

  function waitForElement(finderFn, timeoutSec, queryLabel) {
    return new Promise((resolve) => {
      const timeoutMs = (typeof timeoutSec === 'number' && timeoutSec > 0) ? timeoutSec * 1000 : 0;

      // Immediate check
      try {
        const immediate = finderFn();
        if (immediate && isVisible(immediate)) {
          return resolve(tagElement(immediate));
        }
      } catch(e) {}

      if (timeoutMs <= 0) {
        return resolve(null);
      }

      let resolved = false;
      let observer = null;
      let timer = null;
      let rafId = null;

      function cleanup() {
        if (observer) {
          try { observer.disconnect(); } catch {}
          observer = null;
        }
        if (timer) {
          clearTimeout(timer);
          timer = null;
        }
        if (rafId && typeof cancelAnimationFrame === 'function') {
          cancelAnimationFrame(rafId);
          rafId = null;
        }
      }

      function check() {
        if (resolved) return true;
        try {
          const found = finderFn();
          if (found && isVisible(found)) {
            resolved = true;
            cleanup();
            resolve(tagElement(found));
            return true;
          }
        } catch(e) {}
        return false;
      }

      try {
        if (typeof MutationObserver !== 'undefined') {
          observer = new MutationObserver(() => {
            check();
          });
          const root = document.documentElement || document.body;
          if (root) {
            observer.observe(root, {
              childList: true,
              subtree: true,
              attributes: true,
              characterData: true
            });
          }
        }
      } catch(e) {}

      if (typeof requestAnimationFrame === 'function') {
        const loop = () => {
          if (!check()) {
            rafId = requestAnimationFrame(loop);
          }
        };
        rafId = requestAnimationFrame(loop);
      }

      timer = setTimeout(() => {
        if (resolved) return;
        resolved = true;
        cleanup();

        // Collect fuzzy suggestions
        const suggestions = [];
        try {
          const qLower = String(queryLabel).toLowerCase();
          const all = document.querySelectorAll('button, a, input, select, textarea, [role]');
          for (const el of all) {
            if (!isVisible(el)) continue;
            const txt = (getAccessibleName(el) || el.value || '').trim();
            if (!txt) continue;
            const tLower = txt.toLowerCase();
            if (tLower.includes(qLower) || qLower.includes(tLower)) {
              suggestions.push({
                ref: el.getAttribute('data-cbridge-id') ? '#' + el.getAttribute('data-cbridge-id') : '#element',
                role: getComputedRole(el),
                name: txt.slice(0, 50)
              });
              if (suggestions.length >= 5) break;
            }
          }
        } catch(e) {}

        let autoSnapshot = '';
        try {
          const snapRes = generateSnapshot();
          autoSnapshot = snapRes.snapshot || '';
        } catch(e) {}

        resolve({
          __error: {
            code: 'ELEMENT_NOT_FOUND',
            target: queryLabel,
            suggestions,
            auto_snapshot: autoSnapshot,
            url: window.location.href
          }
        });
      }, timeoutMs);
    });
  }

  switch (operation) {
    case 'find_element': {
      const { query, strategy = 'polymorphic', exact = false, timeout = 1.5 } = args;

      function getFinder() {
        const qLower = typeof query === 'string' ? query.toLowerCase().trim() : '';
        if (strategy === 'text') {
          return () => {
            const elements = document.querySelectorAll('button, a, input[type="button"], input[type="submit"], [role="button"], [role="link"], h1, h2, h3, h4, h5, h6, p, span, li, label, div');
            let fallback = null;
            for (const el of elements) {
              if (!isVisible(el)) continue;
              const name = getAccessibleName(el);
              const txt = el.innerText?.trim() || '';
              if (exact) {
                if (name === query || txt === query) return el;
              } else {
                if (name.toLowerCase().includes(qLower) || txt.toLowerCase().includes(qLower)) {
                  if (['BUTTON', 'A', 'INPUT'].includes(el.tagName) || el.getAttribute('role')) return el;
                  if (!fallback) fallback = el;
                }
              }
            }
            return fallback;
          };
        } else if (strategy === 'input') {
          return () => {
            const inputs = document.querySelectorAll('input:not([type="hidden"]), textarea, select, [contenteditable="true"], [role="textbox"], [role="searchbox"], [role="combobox"]');
            let best = null;
            let bestScore = 0;
            for (const el of inputs) {
              if (!isVisible(el)) continue;
              let score = 0;
              const ph = (el.getAttribute('placeholder') || '').toLowerCase();
              const aria = (el.getAttribute('aria-label') || '').toLowerCase();
              const nm = (el.getAttribute('name') || '').toLowerCase();
              const id = (el.id || '').toLowerCase();
              if (ph === qLower || aria === qLower || nm === qLower || id === qLower) score = 100;
              else if (ph.includes(qLower) || aria.includes(qLower) || nm.includes(qLower)) score = 70;

              if (el.id) {
                try {
                  const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                  if (l && (l.innerText.toLowerCase() === qLower || l.innerText.toLowerCase().includes(qLower))) score = Math.max(score, 95);
                } catch(e) {}
              }
              const pLabel = el.closest('label');
              if (pLabel && (pLabel.innerText.toLowerCase() === qLower || pLabel.innerText.toLowerCase().includes(qLower))) score = Math.max(score, 90);

              if (score > bestScore) {
                bestScore = score;
                best = el;
              }
            }
            return best;
          };
        } else if (strategy === 'button') {
          return () => {
            const buttons = document.querySelectorAll('button, input[type="button"], input[type="submit"], a[role="button"], [role="button"], [role="menuitem"], summary');
            for (const el of buttons) {
              if (!isVisible(el)) continue;
              const name = getAccessibleName(el);
              const txt = el.innerText?.trim() || el.value?.trim() || '';
              if (exact) {
                if (name === query || txt === query) return el;
              } else {
                if (name.toLowerCase().includes(qLower) || txt.toLowerCase().includes(qLower)) return el;
              }
            }
            return null;
          };
        } else if (strategy === 'css') {
          return () => {
            const el = document.querySelector(query);
            return (el && isVisible(el)) ? el : null;
          };
        } else {
          // Polymorphic strategy
          return () => {
            const res = resolveTarget(query);
            if (res && !res.error && res.el && isVisible(res.el)) return res.el;

            // Check CSS if contains CSS selector chars
            if (typeof query === 'string' && (['.', '#', '[', '>', ':'].some(c => query.startsWith(c)) || query.includes(' '))) {
              try {
                const el = document.querySelector(query);
                if (el && isVisible(el)) return el;
              } catch(e) {}
            }

            // Try button
            const buttons = document.querySelectorAll('button, input[type="button"], input[type="submit"], [role="button"]');
            for (const el of buttons) {
              if (isVisible(el) && getAccessibleName(el).toLowerCase().includes(qLower)) return el;
            }

            // Try input
            const inputs = document.querySelectorAll('input:not([type="hidden"]), textarea, select');
            for (const el of inputs) {
              if (isVisible(el)) {
                const ph = (el.getAttribute('placeholder') || '').toLowerCase();
                const nm = (el.getAttribute('name') || '').toLowerCase();
                if (ph.includes(qLower) || nm.includes(qLower)) return el;
              }
            }

            // Try text
            const texts = document.querySelectorAll('a, p, span, h1, h2, h3, h4, li, div');
            for (const el of texts) {
              if (isVisible(el) && (el.innerText?.toLowerCase().includes(qLower) || getAccessibleName(el).toLowerCase().includes(qLower))) {
                return el;
              }
            }
            return null;
          };
        }
      }

      const finder = getFinder();
      return waitForElement(finder, timeout, String(query)).then(res => {
        if (!res) {
          return {
            __error: {
              code: 'ELEMENT_NOT_FOUND',
              target: String(query),
              suggestions: [],
              url: window.location.href
            }
          };
        }
        return res;
      });
    }

    case 'query_elements': {
      const { selector, css_selector } = args;
      const sel = selector || css_selector || '*';
      const nodes = document.querySelectorAll(sel);
      const results = [];
      for (const el of nodes) {
        if (isVisible(el)) {
          results.push(tagElement(el));
        }
      }
      return results;
    }

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
      const { target, state = 'visible', timeout = 10.0 } = args;
      return waitForCondition(target, state, timeout);
    }

    case 'wait_for_url': {
      const { pattern, timeout = 15.0 } = args;
      return waitForUrl(pattern, timeout);
    }

    case 'fill_form': {
      const mapping = args.mapping || args.fields || {};
      const submit = args.submit;
      let filledCount = 0;
      const errors = [];

      function findField(key) {
        const res = resolveTarget(key);
        if (res && res.el && isVisible(res.el)) return res.el;

        const qLower = String(key).toLowerCase();
        const inputs = document.querySelectorAll('input:not([type="hidden"]), textarea, select, [contenteditable="true"], [role="textbox"], [role="searchbox"], [role="combobox"]');
        let best = null;
        let bestScore = 0;
        for (const el of inputs) {
          if (!isVisible(el)) continue;
          let score = 0;
          const ph = (el.getAttribute('placeholder') || '').toLowerCase();
          const aria = (el.getAttribute('aria-label') || '').toLowerCase();
          const nm = (el.getAttribute('name') || '').toLowerCase();
          const id = (el.id || '').toLowerCase();
          if (ph === qLower || aria === qLower || nm === qLower || id === qLower) score = 100;
          else if (ph.includes(qLower) || aria.includes(qLower) || nm.includes(qLower)) score = 70;

          if (el.id) {
            try {
              const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
              if (l && (l.innerText.toLowerCase() === qLower || l.innerText.toLowerCase().includes(qLower))) score = Math.max(score, 95);
            } catch(e) {}
          }
          const pLabel = el.closest('label');
          if (pLabel && (pLabel.innerText.toLowerCase() === qLower || pLabel.innerText.toLowerCase().includes(qLower))) score = Math.max(score, 90);

          if (score > bestScore) {
            bestScore = score;
            best = el;
          }
        }
        return best;
      }

      for (const [key, value] of Object.entries(mapping)) {
        const el = findField(key);
        if (!el) {
          errors.push({ field: key, error: 'Field not found' });
          continue;
        }
        const tag = el.tagName.toLowerCase();
        const type = (el.type || '').toLowerCase();
        const role = (el.getAttribute('role') || '').toLowerCase();

        if (typeof value === 'boolean') {
          const isChecked = !!el.checked || el.getAttribute('aria-checked') === 'true';
          if (isChecked !== value) {
            el.click();
          }
        } else if (type === 'radio' || role === 'radio') {
          el.click();
        } else if (tag === 'select' || role === 'combobox' || Array.isArray(value)) {
          const targetVal = String(Array.isArray(value) ? value[0] : value);
          let foundOption = false;
          if (el.options) {
            for (let i = 0; i < el.options.length; i++) {
              if (el.options[i].value === targetVal || el.options[i].text.trim() === targetVal) {
                el.selectedIndex = i;
                foundOption = true;
                break;
              }
            }
          }
          if (!foundOption) el.value = targetVal;
          el.dispatchEvent(new Event('change', { bubbles: true }));
        } else {
          el.focus();
          el.value = String(value);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        filledCount++;
      }

      let submitted = false;
      if (submit) {
        if (typeof submit === 'string') {
          const qLower = submit.toLowerCase();
          const buttons = document.querySelectorAll('button, input[type="submit"], input[type="button"], a[role="button"], [role="button"]');
          for (const btn of buttons) {
            if (!isVisible(btn)) continue;
            const name = getAccessibleName(btn).toLowerCase();
            if (name === qLower || name.includes(qLower)) {
              btn.click();
              submitted = true;
              break;
            }
          }
        } else if (submit === true) {
          const btn = document.querySelector('button[type="submit"], input[type="submit"]');
          if (btn) {
            btn.click();
            submitted = true;
          } else {
            const form = document.querySelector('form');
            if (form) {
              form.requestSubmit ? form.requestSubmit() : form.submit();
              submitted = true;
            }
          }
        }
      }

      return { status: 'ok', action: 'fill_form', filledCount, totalFields: Object.keys(mapping).length, submitted, errors };
    }

    case 'extract_items': {
      const itemSelector = args.itemSelector || args.item_selector || 'article, tr, li, .item, .card';
      const fields = args.fields || {};
      const items = [];
      const nodes = document.querySelectorAll(itemSelector);

      for (const node of nodes) {
        if (!isVisible(node)) continue;
        const record = {};
        for (const [fieldKey, fieldQuery] of Object.entries(fields)) {
          if (!fieldQuery) continue;
          let subSelector = fieldQuery;
          let attrName = null;
          if (typeof fieldQuery === 'string' && fieldQuery.includes('@')) {
            const parts = fieldQuery.split('@');
            subSelector = parts[0];
            attrName = parts[1];
          }

          let targetNode = node;
          if (subSelector && subSelector.trim()) {
            targetNode = node.querySelector(subSelector);
          }

          if (!targetNode) {
            record[fieldKey] = null;
          } else if (attrName) {
            record[fieldKey] = targetNode.getAttribute(attrName);
          } else {
            record[fieldKey] = (targetNode.innerText || targetNode.textContent || '').trim();
          }
        }
        items.push(record);
      }
      return { status: 'ok', action: 'extract_items', count: items.length, items };
    }

    case 'highlight_refs': {
      const existing = document.getElementById('__ag_ref_overlay__');
      if (existing) {
        existing.remove();
        return { active: false };
      }
      if (!window.__AG_REGISTRY__?.refMap || window.__AG_REGISTRY__.refMap.size === 0) {
        generateSnapshot();
      }
      const refMap = window.__AG_REGISTRY__?.refMap || new Map();
      const overlay = document.createElement('div');
      overlay.id = '__ag_ref_overlay__';
      overlay.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647;font-family:ui-monospace,SFMono-Regular,monospace;';

      let visibleCount = 0;
      for (const [refId, el] of refMap.entries()) {
        if (!el || !el.isConnected) continue;
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < window.innerHeight && rect.right > 0 && rect.left < window.innerWidth) {
          visibleCount++;
          const badge = document.createElement('div');
          badge.style.cssText = `position:fixed;left:${Math.max(2, rect.left)}px;top:${Math.max(2, rect.top - 18)}px;background:#0ea5e9;color:#041e3a;font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;border:1px solid #38bdf8;box-shadow:0 2px 6px rgba(0,0,0,0.5);pointer-events:none;z-index:2147483647;line-height:1.2;`;
          badge.textContent = `#${refId}`;

          const box = document.createElement('div');
          box.style.cssText = `position:fixed;left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px;border:1.5px dashed #0ea5e9;background:rgba(14,165,233,0.08);border-radius:3px;pointer-events:none;z-index:2147483646;box-sizing:border-box;`;

          overlay.appendChild(box);
          overlay.appendChild(badge);
        }
      }
      document.documentElement.appendChild(overlay);
      setTimeout(() => {
        const el = document.getElementById('__ag_ref_overlay__');
        if (el) el.remove();
      }, 10000);
      return { active: true, count: visibleCount, total: refMap.size };
    }

    case 'get_metrics': {
      const readyState = document.readyState;
      const refCount = window.__AG_REGISTRY__?.totalInteractive || (window.__AG_REGISTRY__?.refMap?.size || 0);
      const viewport = `${window.innerWidth} × ${window.innerHeight}`;
      const totalElements = document.querySelectorAll('*').length;
      return { readyState, refCount, viewport, totalElements, url: window.location.href, title: document.title };
    }

    default:
      return { __error: { message: `Unknown inPage operation: ${operation}` } };
  }
}
