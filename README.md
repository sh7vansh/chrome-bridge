# Chrome Bridge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-blue)](README.md)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](pyproject.toml)
[![Chrome MV3](https://img.shields.io/badge/Chrome-MV3-blue)](extension/manifest.json)

Connect AI agents directly to your real, logged-in Google Chrome browser.

Unlike Puppeteer or Playwright which launch isolated, empty browser instances, Chrome Bridge connects to your existing browser session:
- **Live User Session:** Retains all cookies, logins, credentials, and active tab states (Gmail, GitHub, internal dashboards).
- **Zero Open Ports:** Communicates exclusively over OS standard input/output (`stdio`) via Chrome Native Messaging. No local web servers or open network listeners.
- **99% Token Reduction:** Translates full DOM trees into compact text outlines with numbered interactive reference IDs (`[#1]`, `[#2]`).
- **Stateful Python REPL:** Agents write procedural Python in a persistent runtime where state, variables, and tab bindings persist across turns.

---

## Architecture & Request Flow

```mermaid
sequenceDiagram
    autonumber
    actor Agent as AI Agent (Claude / Cursor / Antigravity)
    participant REPL as Python Runtime (chrome_sdk)
    participant Host as Native Host (stdio IPC)
    participant Ext as Chrome MV3 Extension
    participant Tab as Live Chrome Tab (DOM & Shadow DOM)

    Agent->>REPL: execute_python("chrome.click(14)")
    Note over REPL: Resolves active tab & serializes JSON packet
    REPL->>Host: JSON message via length-prefixed stdio
    Host->>Ext: Chrome Native Messaging port
    Ext->>Tab: Dispatches trusted event / queries Shadow DOM
    Tab-->>Ext: Element updated / DOM mutated
    Ext-->>Host: Action ack & distilled Ref-ID delta
    Host-->>REPL: stdio response stream
    REPL-->>Agent: Action return value / refreshed snapshot outline
```

```mermaid
flowchart LR
    subgraph ClientLayer ["AI & Client Runtime"]
        A["AI Agent<br/>(Claude / Cursor / Antigravity)"]
        B["Python REPL Runtime<br/>(chrome_sdk)"]
        A -->|"execute_python(code)"| B
    end

    subgraph NativeBridge ["OS Native Bridge"]
        C["Native Messaging Host<br/>(native-host.mjs / stdio)"]
        B -->|"Length-prefixed stdio"| C
    end

    subgraph BrowserEngine ["Chrome Browser (Live Session)"]
        D["MV3 Extension Service Worker"]
        E["Active Tab & Content Scripts<br/>(DOM, Shadow DOM, Ref-IDs)"]
        C -->|"Native Messaging Port"| D
        D -->|"chrome.tabs / scripting"| E
    end
```

---

## Installation (2 Minutes)

### 1. Install Runtime & Register Native Host

Run the setup script for your operating system:

```bash
# macOS & Linux
git clone https://github.com/sh7vansh/chrome-bridge.git && cd chrome-bridge && ./setup.sh
```

```powershell
# Windows (PowerShell)
git clone https://github.com/sh7vansh/chrome-bridge.git; cd chrome-bridge; .\setup.ps1
```

```bash
# Or via npx
npx antigravity-chrome-bridge setup
```

### 2. Load Extension in Chrome

1. Open Google Chrome and go to `chrome://extensions`.
2. Enable **Developer mode** using the toggle in the top-right corner.
3. Click **Load unpacked** (top-left) and select the `extension/` directory inside this repository.
4. The Chrome Bridge icon in your browser toolbar will indicate a connected state.

### 3. Connect AI Clients (MCP)

Add the server entry to your MCP client configuration (`claude_desktop_config.json`, Cursor MCP settings, or Antigravity):

```json
{
  "mcpServers": {
    "chrome-bridge": {
      "command": "python3",
      "args": ["/path/to/chrome-bridge/mcp_server.py"]
    }
  }
}
```

---

## Python SDK Quick Reference

The synchronous `chrome` client is ready to use directly in Python scripts and agent REPL sessions:

```python
from chrome_sdk import chrome

# Inspect current page structure with numbered Ref-IDs
print(chrome.snapshot())

# Click button or link by element ID
chrome.click(12)

# Type into input field and submit
chrome.type(3, "Search query", press_enter=True)

# Select dropdown option
chrome.select(5, "option_value")

# Multimedia fast-path (Shadow-DOM & audio/video)
chrome.media.play_pause()
chrome.media.seek(30)

# Tab management
tab = chrome.new_tab("https://github.com")
print(chrome.tabs)
```

### Core API Methods

| Method | Syntax | Description |
| :--- | :--- | :--- |
| `snapshot` | `chrome.snapshot()` | Returns a distilled text outline of interactive elements with `[#id]` references |
| `click` | `chrome.click(id)` | Dispatches a click event to the target Ref-ID or CSS selector |
| `type` | `chrome.type(id, text, press_enter=False)` | Focuses target input and inputs text with optional Enter keypress |
| `select` | `chrome.select(id, value)` | Chooses an option in a `<select>` dropdown |
| `hover` | `chrome.hover(id)` | Triggers mouse hover state on target element |
| `scroll` | `chrome.scroll(x=0, y=500)` | Scrolls active page viewport |
| `navigate` | `chrome.navigate(url)` | Navigates active tab to specified URL |
| `new_tab` | `chrome.new_tab(url)` | Opens a new browser tab |
| `tabs` | `chrome.tabs` | Returns list of all open tabs with IDs and URLs |
| `eval_js` | `chrome.eval_js(expr)` | Executes JavaScript expression in page context and returns result |
| `screenshot` | `chrome.screenshot()` | Returns base64 PNG data of current tab |
| `media` | `chrome.media.play_pause()` | Controls active HTML5 video/audio playback |

---

## Testing

Run the test suite to verify the native host and SDK bindings:

```bash
./test.sh
# or
pytest tests/
```

---

## Security & Architecture Principles

- **Local-Only Communication:** All data transfer occurs over local standard I/O pipes. No data leaves your machine.
- **No Cloud Proxies:** All browsing sessions execute against your local Chrome application directly.
- **Bot-Detection Immunity:** Operates within your actual user profile and existing session cookies without triggering automation or CAPTCHA defenses.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
