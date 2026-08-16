# Chrome Bridge for AI Agents (MCP Server & Extension)

A lightweight, zero-configuration Model Context Protocol (MCP) server and Chrome Extension that enables AI assistants (Antigravity, Claude Desktop, Cursor, etc.) to automate and inspect your active everyday Google Chrome browser in real-time.

---

## 🌟 Features

- **Zero Background Daemons**: The MCP server runs strictly on-demand when your AI client is active and shuts down when you exit.
- **Everyday Profile**: Works with your regular Chrome profile (passwords, logins, cookies intact) without requiring debug flags or isolated browser instances.
- **Full Automation Suite**:
  - `chrome_list_tabs` & `chrome_get_active_tab`
  - `chrome_navigate` (new tab or active tab)
  - `chrome_click` (CSS selectors with auto scroll-into-view)
  - `chrome_type` (inputs, textareas, clear, press Enter)
  - `chrome_get_page_content` (semantic text and headers)
  - `chrome_screenshot` (PNG capture)
  - `chrome_execute_script` (execute JavaScript in page context)
  - `chrome_scroll`, `chrome_switch_tab`, `chrome_close_tab`

---

## 📦 How to Share & Install

### 1. Register Native Messaging Host
```bash
npm run setup
```
*(This registers the native messaging manifest with Chrome/Chromium/Brave)*

### 2. Load the Chrome Extension
1. Open Google Chrome and go to `chrome://extensions`.
2. Enable **Developer mode** (toggle in top right).
3. Click **Load unpacked** and select the `extension/` folder.
4. The extension icon will appear in your toolbar showing **`🟢 Native Bridge`**.

### 2. Configure Your AI Client (Antigravity, Claude, Cursor)

Add the MCP server to your MCP configuration (e.g. `~/.agent/mcp_config.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "chrome-bridge": {
      "command": "node",
      "args": ["/path/to/antigravity-chrome-bridge/mcp-server.mjs"]
    }
  }
}
```

### 3. That's It!
Whenever your AI agent needs to interact with your browser, it will spawn the MCP server on demand. When your session ends, the process terminates and frees all resources.

---

## 🛠️ CLI Usage (Optional)

You can also run standalone commands via `ctl.mjs`:

```bash
# Get active tab details
node ctl.mjs active

# Navigate
node ctl.mjs nav "https://news.ycombinator.com"

# Capture screenshot
node ctl.mjs screenshot /tmp/tab.png
```
