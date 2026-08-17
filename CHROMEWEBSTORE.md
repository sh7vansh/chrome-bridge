# Chrome Web Store Listing — Chrome Bridge

> Last Updated: 2026-08-18

---

## 📝 Store Listing Details

**Extension Name**
Chrome Bridge

**Short Description (Max 132 chars)**
Connects your standard Google Chrome browser to AI coding assistants and Python runtime via Model Context Protocol (MCP).

**Detailed Description**
Chrome Bridge seamlessly connects your active Google Chrome browser to local AI coding assistants and agents (such as Claude Desktop, Cursor, and Antigravity) using the open Model Context Protocol (MCP).

Key Capabilities:
- Seamless Navigation: Automates navigation across web pages and tabs without opening isolated/debug browsers.
- Real-time DOM Inspection: Reads semantic page content, headings, forms, and articles for AI analysis.
- UI Automation: Enables AI assistants to click buttons, fill input fields, and scroll pages.
- Visual Verification: Captures full viewport screenshots for visual debugging and UI layout reviews.
- CDP Script Execution: Evaluates JavaScript expressions in real-time via Chrome DevTools Protocol.

How It Works:
1. Install the extension in Google Chrome.
2. Run the companion MCP host script on your machine (`npm run setup`).
3. Add the MCP server configuration to your AI assistant.
4. Your AI agent can now inspect and automate your browser sessions on demand.

Privacy & Security:
- 100% Local: All communication happens directly on your machine via local Native Messaging IPC.
- No External Servers: No telemetry, browsing data, or keystrokes are transmitted to any remote servers.

---

**Category**
Developer Tools

**Single Purpose**
Enables local AI coding assistants to automate and inspect web pages in Google Chrome via local Model Context Protocol (MCP) IPC.

**Primary Language**
English

---

## 🛡️ Permissions Justification (Required for Review Approval)

| Permission | Type | Justification |
| :--- | :--- | :--- |
| `nativeMessaging` | `permissions` | Required to exchange automation commands and responses with the local MCP server process (`native-host.mjs`) on the user's machine over stdio. |
| `scripting` | `permissions` | Required to programmatically inspect page DOM elements, read semantic article text, and interact with form inputs as requested by the user's AI assistant. |
| `tabs` | `permissions` | Required to query open browser tabs, retrieve active tab metadata (URL and title), and navigate tabs on behalf of the user. |
| `activeTab` | `permissions` | Required to access and interact with the currently focused tab when invoked by the user. |
| `debugger` | `permissions` | Required to execute JavaScript expressions and inspect pages via Chrome DevTools Protocol (`Runtime.evaluate`), ensuring execution on strict Content Security Policy (CSP) websites. |
| `storage` | `permissions` | Required to store user settings and maintain a local in-memory activity stream in the popup. |
| `alarms` | `permissions` | Required to periodically verify Native Messaging connection health with the local host. |
| `<all_urls>` | `host_permissions` | Required so the AI assistant can automate browser actions across arbitrary user-specified websites during coding and web development tasks. |

---

## 🔒 Privacy & Data Use Disclosures

- **Data Collection:** NO personal data is collected or transmitted off-device.
- **Data Sharing:** NO data is sold or shared with third parties.
- **Website Content:** Website text and screenshots are only read locally upon explicit request from the user's local AI agent.

---

## 📦 How to Package for Chrome Web Store Submission

1. Ensure the manifest and icons are ready:
   - `manifest.json`
   - `background.js`
   - `popup.html` & `popup.js`
   - `icons/icon-16.png`, `icons/icon-48.png`, `icons/icon-128.png`
2. Create the submission zip containing ONLY the extension folder files:
   ```bash
   cd extension
   zip -r ../chrome-bridge-extension.zip *
   ```
3. Upload `chrome-bridge-extension.zip` to the [Chrome Developer Dashboard](https://chrome.google.com/webstore/devconsole).
