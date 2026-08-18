document.addEventListener('DOMContentLoaded', async () => {
  // Navigation elements
  const tabStreamBtn = document.getElementById('tabStreamBtn');
  const tabInspectorBtn = document.getElementById('tabInspectorBtn');
  const tabBridgeBtn = document.getElementById('tabBridgeBtn');
  
  const panelStream = document.getElementById('panelStream');
  const panelInspector = document.getElementById('panelInspector');
  const panelBridge = document.getElementById('panelBridge');
  
  // Header / Top elements
  const statusPill = document.getElementById('statusPill');
  const statusLabel = document.getElementById('statusLabel');
  const activeTabTitle = document.getElementById('activeTabTitle');
  const activeTabId = document.getElementById('activeTabId');
  const activeTabUrl = document.getElementById('activeTabUrl');
  const tabFaviconWrap = document.getElementById('tabFaviconWrap');
  const logCountBadge = document.getElementById('logCountBadge');
  
  // Stream & Filter elements
  const streamList = document.getElementById('streamList');
  const clearStreamBtn = document.getElementById('clearStreamBtn');
  const filterChips = document.querySelectorAll('.filter-chip');
  
  // Inspector elements
  const metricRefCount = document.getElementById('metricRefCount');
  const metricReadyState = document.getElementById('metricReadyState');
  const metricViewport = document.getElementById('metricViewport');
  const metricNodeCount = document.getElementById('metricNodeCount');
  const highlightRefsBtn = document.getElementById('highlightRefsBtn');
  const copySnapshotBtn = document.getElementById('copySnapshotBtn');
  const refreshSnapshotBtn = document.getElementById('refreshSnapshotBtn');
  const snapshotPreviewBox = document.getElementById('snapshotPreviewBox');
  
  // Bridge elements
  const bridgeLatency = document.getElementById('bridgeLatency');
  const reconnectNativeBtn = document.getElementById('reconnectNativeBtn');
  const copyPythonSnippetBtn = document.getElementById('copyPythonSnippetBtn');
  const copyMcpBtn = document.getElementById('copyMcpBtn');
  const toast = document.getElementById('toast');
  const toastMsg = document.getElementById('toastMsg');

  let currentFilter = 'all';
  let cachedLogs = [];
  let currentActiveTabId = null;
  let isHighlightActive = false;
  let lastPingMs = null;

  // --- Tab Navigation ---
  function switchTab(activeBtn, activePanel) {
    [tabStreamBtn, tabInspectorBtn, tabBridgeBtn].forEach(btn => btn.classList.remove('active'));
    [panelStream, panelInspector, panelBridge].forEach(panel => panel.classList.remove('active'));
    
    activeBtn.classList.add('active');
    activePanel.classList.add('active');

    if (activePanel === panelInspector) {
      refreshInspectorData();
    }
  }

  tabStreamBtn.addEventListener('click', () => switchTab(tabStreamBtn, panelStream));
  tabInspectorBtn.addEventListener('click', () => switchTab(tabInspectorBtn, panelInspector));
  tabBridgeBtn.addEventListener('click', () => switchTab(tabBridgeBtn, panelBridge));

  // --- Filter Chips ---
  filterChips.forEach(chip => {
    chip.addEventListener('click', () => {
      filterChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      currentFilter = chip.dataset.filter || 'all';
      renderLogs(cachedLogs);
    });
  });

  // --- Render Telemetry Logs ---
  function renderLogs(logs) {
    cachedLogs = logs;
    logCountBadge.textContent = logs.length;

    const filtered = logs.filter(log => {
      const type = (log.type || 'info').toLowerCase();
      if (currentFilter === 'all') return true;
      if (currentFilter === 'actions') return ['click', 'type', 'nav', 'eval', 'scroll', 'tabs', 'cmd'].includes(type);
      if (currentFilter === 'dom') return ['content', 'screenshot'].includes(type);
      if (currentFilter === 'errors') return type === 'error';
      return true;
    });

    if (!filtered.length) {
      streamList.innerHTML = `
        <div class="empty-state">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="2" y="3" width="20" height="14" rx="2"></rect>
            <line x1="8" y1="21" x2="16" y2="21"></line>
            <line x1="12" y1="17" x2="12" y2="21"></line>
          </svg>
          <div class="empty-state-title">No events matching "${currentFilter}"</div>
          <div class="empty-state-sub">Browser automation telemetry will stream here in real-time.</div>
        </div>
      `;
      return;
    }

    streamList.innerHTML = filtered.map(l => {
      const type = (l.type || 'info').toLowerCase();
      const tagClass = `tag-${type}`;
      const tagLabel = type.toUpperCase();
      const hasDetails = Boolean(l.details);

      return `
        <div class="stream-item ${hasDetails ? 'has-details' : ''}" data-log-id="${l.id}">
          <div class="stream-row-main">
            <span class="tag-badge ${tagClass}">${escapeHtml(tagLabel)}</span>
            <span class="stream-content" title="${escapeHtml(l.message)}">${escapeHtml(l.message)}</span>
            <span class="stream-time">${escapeHtml(l.timestamp)}</span>
          </div>
          ${hasDetails ? `<div class="stream-payload-box">${escapeHtml(l.details)}</div>` : ''}
        </div>
      `;
    }).join('');

    // Toggle expand for details
    streamList.querySelectorAll('.stream-item.has-details').forEach(item => {
      item.addEventListener('click', () => {
        item.classList.toggle('expanded');
      });
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // --- Inspector Data Fetching ---
  async function refreshInspectorData() {
    if (!currentActiveTabId) return;

    chrome.runtime.sendMessage({ type: 'GET_PAGE_METRICS', tabId: currentActiveTabId }, (res) => {
      if (chrome.runtime.lastError || !res || !res.success) return;
      const m = res.metrics || {};
      metricRefCount.textContent = m.refCount || '0';
      metricReadyState.textContent = m.readyState || 'complete';
      metricViewport.textContent = m.viewport || '-';
      metricNodeCount.textContent = (m.totalElements || 0).toLocaleString();
    });

    chrome.runtime.sendMessage({ type: 'CAPTURE_SNAPSHOT', tabId: currentActiveTabId }, (res) => {
      if (chrome.runtime.lastError || !res || !res.success) {
        snapshotPreviewBox.textContent = 'Snapshot unavailable for this tab.';
        return;
      }
      snapshotPreviewBox.textContent = res.snapshot ? res.snapshot.slice(0, 1200) + (res.snapshot.length > 1200 ? '\n...[truncated]' : '') : 'Empty snapshot';
    });
  }

  // --- Status & Telemetry Polling ---
  async function refreshStatus() {
    const pingStart = performance.now();
    chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (response) => {
      const pingDuration = (performance.now() - pingStart).toFixed(1);
      lastPingMs = pingDuration;
      bridgeLatency.textContent = `⚡ ${pingDuration}ms`;

      if (chrome.runtime.lastError || !response) {
        statusPill.className = 'status-pill';
        statusLabel.textContent = 'Standby';
        return;
      }

      if (response.isConnected) {
        statusPill.className = 'status-pill connected';
        statusLabel.textContent = 'Connected';
      } else {
        statusPill.className = 'status-pill';
        statusLabel.textContent = 'Standby';
      }

      if (response.activeTab) {
        currentActiveTabId = response.activeTab.id;
        activeTabTitle.textContent = response.activeTab.title || 'Untitled';
        activeTabTitle.title = response.activeTab.title || '';
        activeTabId.textContent = `#${response.activeTab.id}`;
        activeTabUrl.textContent = response.activeTab.url || 'chrome://newtab';
        activeTabUrl.title = response.activeTab.url || '';

        if (response.activeTab.favIconUrl) {
          tabFaviconWrap.innerHTML = `<img src="${escapeHtml(response.activeTab.favIconUrl)}" alt="icon" onerror="this.style.display='none'">`;
        }
      }

      if (response.activityLogs) {
        renderLogs(response.activityLogs);
      }
    });
  }

  // Initial load
  const { activityLogs = [] } = await chrome.storage.local.get('activityLogs');
  renderLogs(activityLogs);
  await refreshStatus();

  const pollInterval = setInterval(refreshStatus, 1400);
  window.addEventListener('unload', () => clearInterval(pollInterval));

  // --- Interactive Actions ---

  // Highlight Ref-IDs
  highlightRefsBtn.addEventListener('click', () => {
    if (!currentActiveTabId) return;
    chrome.runtime.sendMessage({ type: 'HIGHLIGHT_REFS', tabId: currentActiveTabId }, (res) => {
      if (res && res.success) {
        isHighlightActive = res.active;
        if (isHighlightActive) {
          highlightRefsBtn.classList.add('active-tool');
          showToast(`Highlighted ${res.count || 0} Ref-IDs on page`);
        } else {
          highlightRefsBtn.classList.remove('active-tool');
          showToast('Highlight overlay cleared');
        }
      } else {
        showToast('Could not highlight on this page');
      }
    });
  });

  // Copy Semantic DOM Snapshot
  copySnapshotBtn.addEventListener('click', () => {
    if (!currentActiveTabId) return;
    chrome.runtime.sendMessage({ type: 'CAPTURE_SNAPSHOT', tabId: currentActiveTabId }, async (res) => {
      if (res && res.success && res.snapshot) {
        try {
          await navigator.clipboard.writeText(res.snapshot);
          showToast('Snapshot copied to clipboard!');
        } catch {
          showToast('Failed to copy snapshot');
        }
      } else {
        showToast('Snapshot unavailable for this tab');
      }
    });
  });

  // Refresh Snapshot Preview
  refreshSnapshotBtn.addEventListener('click', () => {
    refreshInspectorData();
    showToast('Refreshed page metrics');
  });

  // Clear Stream
  clearStreamBtn.addEventListener('click', async () => {
    await chrome.storage.local.set({ activityLogs: [] });
    renderLogs([]);
    showToast('Activity feed cleared');
  });

  // Reconnect Bridge
  reconnectNativeBtn.addEventListener('click', () => {
    statusPill.className = 'status-pill connecting';
    statusLabel.textContent = 'Connecting...';
    chrome.runtime.sendMessage({ type: 'RECONNECT' }, () => {
      setTimeout(refreshStatus, 400);
    });
    showToast('Reconnecting Native Host Bridge...');
  });

  // Copy 1-Step Setup Command
  const copySetupCmdBtn = document.getElementById('copySetupCmdBtn');
  if (copySetupCmdBtn) {
    copySetupCmdBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText('uvx antigravity-chrome-bridge setup');
        showToast('Copied setup command!');
      } catch {
        showToast('Could not copy automatically');
      }
    });
  }

  // Copy Python Snippet
  copyPythonSnippetBtn.addEventListener('click', async () => {
    const pythonCode = `from chrome_sdk import chrome\n\n# Open or inspect active tab\nprint(chrome.url)\nprint(chrome.title)\n\n# Take snapshot or click elements\nsnapshot = chrome.snapshot()\n# chrome.click(1)\n`;
    try {
      await navigator.clipboard.writeText(pythonCode);
      showToast('Copied Python snippet!');
    } catch {
      showToast('Could not copy automatically');
    }
  });

  // Copy MCP Config
  copyMcpBtn.addEventListener('click', async () => {
    const mcpConfig = {
      mcpServers: {
        "chrome-bridge": {
          "command": "uvx",
          "args": ["antigravity-chrome-bridge", "mcp"]
        }
      }
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(mcpConfig, null, 2));
      showToast('Copied MCP Config JSON!');
    } catch {
      showToast('Could not copy automatically');
    }
  });

  // Toast Helper
  let toastTimer = null;
  function showToast(msg) {
    toastMsg.textContent = msg;
    toast.classList.add('show');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove('show');
    }, 2200);
  }
});
