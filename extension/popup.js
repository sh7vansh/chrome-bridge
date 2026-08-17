document.addEventListener('DOMContentLoaded', async () => {
  // DOM Elements
  const statusPill = document.getElementById('statusPill');
  const statusLabel = document.getElementById('statusLabel');
  const activeTabTitle = document.getElementById('activeTabTitle');
  const activeTabId = document.getElementById('activeTabId');
  const activeTabUrl = document.getElementById('activeTabUrl');
  const tabFaviconWrap = document.getElementById('tabFaviconWrap');

  const tabStreamBtn = document.getElementById('tabStreamBtn');
  const tabSettingsBtn = document.getElementById('tabSettingsBtn');
  const panelStream = document.getElementById('panelStream');
  const panelSettings = document.getElementById('panelSettings');
  const logCountBadge = document.getElementById('logCountBadge');

  const streamList = document.getElementById('streamList');
  const clearStreamBtn = document.getElementById('clearStreamBtn');

  const reconnectNativeBtn = document.getElementById('reconnectNativeBtn');
  const copyMcpBtn = document.getElementById('copyMcpBtn');
  const toast = document.getElementById('toast');

  // Tab switching
  tabStreamBtn.addEventListener('click', () => {
    tabStreamBtn.classList.add('active');
    tabSettingsBtn.classList.remove('active');
    panelStream.classList.add('active');
    panelSettings.classList.remove('active');
  });

  tabSettingsBtn.addEventListener('click', () => {
    tabSettingsBtn.classList.add('active');
    tabStreamBtn.classList.remove('active');
    panelSettings.classList.add('active');
    panelStream.classList.remove('active');
  });

  // Render logs
  function renderLogs(logs) {
    logCountBadge.textContent = logs.length;
    if (!logs.length) {
      streamList.innerHTML = `
        <div class="empty-state">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="2" y="3" width="20" height="14" rx="2"></rect>
            <line x1="8" y1="21" x2="16" y2="21"></line>
            <line x1="12" y1="17" x2="12" y2="21"></line>
          </svg>
          <div class="empty-state-title">Waiting for AI agent actions</div>
          <div class="empty-state-sub">Browser events will appear here in real-time.</div>
        </div>
      `;
      return;
    }

    streamList.innerHTML = logs.map(l => {
      const type = (l.type || 'info').toLowerCase();
      const tagClass = `tag-${type}`;
      const tagLabel = type.toUpperCase();

      return `
        <div class="stream-item">
          <span class="tag-badge ${tagClass}">${escapeHtml(tagLabel)}</span>
          <span class="stream-content">${escapeHtml(l.message)}</span>
          <span class="stream-time">${escapeHtml(l.timestamp)}</span>
        </div>
      `;
    }).join('');
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  const { activityLogs = [] } = await chrome.storage.local.get('activityLogs');
  renderLogs(activityLogs);

  // Poll status from background service worker
  async function refreshStatus() {
    chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (response) => {
      if (chrome.runtime.lastError || !response) {
        statusPill.className = 'status-pill';
        statusLabel.textContent = 'Standby';
        return;
      }

      if (response.isConnected) {
        statusPill.className = 'status-pill connected';
        statusLabel.textContent = 'Native Bridge';
      } else {
        statusPill.className = 'status-pill';
        statusLabel.textContent = 'Standby';
      }

      if (response.activeTab) {
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

  await refreshStatus();
  const pollInterval = setInterval(refreshStatus, 1200);
  window.addEventListener('unload', () => clearInterval(pollInterval));

  // Reconnect Native Host Action
  if (reconnectNativeBtn) {
    reconnectNativeBtn.addEventListener('click', () => {
      statusPill.className = 'status-pill connecting';
      statusLabel.textContent = 'Connecting...';
      chrome.runtime.sendMessage({ type: 'RECONNECT' }, () => {
        setTimeout(refreshStatus, 400);
      });
      showToast('Reconnecting Native Bridge...');
    });
  }

  // Clear Feed Action
  clearStreamBtn.addEventListener('click', async () => {
    await chrome.storage.local.set({ activityLogs: [] });
    renderLogs([]);
    showToast('Activity feed cleared');
  });

  // Copy MCP Config
  copyMcpBtn.addEventListener('click', async () => {
    const mcpConfig = {
      mcpServers: {
        "chrome-bridge": {
          "command": "python3",
          "args": ["/path/to/antigravity-chrome-bridge/mcp_server.py"]
        }
      }
    };

    try {
      await navigator.clipboard.writeText(JSON.stringify(mcpConfig, null, 2));
      showToast('Copied MCP Config to Clipboard!');
    } catch {
      showToast('Could not copy automatically');
    }
  });

  // Toast Helper
  let toastTimer = null;
  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add('show');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove('show');
    }, 2200);
  }
});
