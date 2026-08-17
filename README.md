# Antigravity Chrome Bridge 2.0 (Persistent Python REPL Runtime)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Cross-Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows%20%7C%20Linux-brightgreen)](README.md)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)](pyproject.toml)

A high-performance Model Context Protocol (MCP) server and Chrome Extension providing a **stateful, persistent in-memory Python REPL runtime** to control and inspect your active Google Chrome browser in real-time.

Instead of orchestrating dozens of discrete tools across multiple latency-heavy round-trips, AI agents (Antigravity, Claude Desktop, Cursor, Gemini) execute procedural Python scripts via a single unified MCP tool: **`execute_python(code)`**.

---

## 🌟 Key Features

- **Persistent Python REPL Session**: Variables, functions, imports, and dataframes defined in turn 1 persist seamlessly into subsequent turns.
- **Cross-Platform Parity**: Full support for **macOS, Windows, and Linux** with automated Windows Registry configuration and platform-aware IPC.
- **Token-Distilled Semantic DOM Snapshots**: In-page `TreeWalker` traversal with AccName 1.2 name computation and visibility filtering delivers **99%+ token reduction** over raw DOM trees.
- **Lightweight Indexed Ref-IDs**: Actionable elements receive 1-based sequential Ref-IDs (`[#1]`, `[#2]`), eliminating brittle selectors and coordinate hallucination.
- **Polymorphic Locator Dispatch**: SDK methods accept integer Ref-IDs (`14`), token strings (`"[#14]"` / `"#14"`), or standard CSS selectors (`"button.submit"`).
- **Single-Turn Self-Healing Diagnostics**:
  - Auto-injected `[diagnostic_auto_snapshot]` on unhandled browser exceptions.
  - Fuzzy near-match candidate suggestions for stale Ref-IDs (`Did you mean: [#18] (button 'Submit')?`).
  - Coordinate hit-testing with interceptor detection (modals, overlays, cookie banners).
  - Actionable checklist prompts on browser disconnection.
- **Works with Your Everyday Profile**: Connects to your active, logged-in browser session (passwords, logins, cookies intact) via native IPC with zero bot detection or port exposure.

---

## 📦 Quick Start & Installation (60 Seconds)

### 1. Run Setup

#### Option A: One-Command via npx
```bash
npx antigravity-chrome-bridge setup
```

#### Option B: Clone & Run Script
- **macOS / Linux:**
  ```bash
  git clone https://github.com/sh7vansh/chrome-bridge.git
  cd chrome-bridge
  ./setup.sh
  ```
- **Windows (PowerShell):**
  ```powershell
  git clone https://github.com/sh7vansh/chrome-bridge.git
  cd chrome-bridge
  .\setup.ps1
  ```

> **What the installer automates:**
> - Probes Python 3.10+ and provisions `.venv` dependencies.
> - Registers Native Messaging manifests (or Windows Registry `HKCU` keys on Windows).
> - Auto-discovers and configures MCP in **Claude Desktop**, **Antigravity CLI**, and **Cursor**.

### 2. Load the Chrome Extension

1. Open Google Chrome (or Brave / Edge) and navigate to `chrome://extensions`.
2. Enable **Developer mode** (toggle in top right).
3. Click **Load unpacked** and select the `chrome-bridge/extension` directory.
4. The extension icon will appear in your toolbar showing **`🟢 Native Bridge`**.

### 3. Verification

Run the test suite anytime:
```bash
.venv/bin/pytest tests/
# or
npm test
```

---

## 💻 Python SDK Cheat Sheet (`chrome`)

The synchronous `chrome` module is pre-injected into every REPL session:

```python
# 1. Orientation & Snapshot
snapshot = chrome.snapshot()
print(snapshot)

# 2. Polymorphic Element Actions
chrome.click(14)                                              # Integer Ref-ID
chrome.click("[#14]")                                         # Ref-ID token
chrome.type("[#2]", "query test", clear=True, press_enter=True)
chrome.select("[#5]", "option_value")                         # Dropdowns
chrome.hover("[#8]")
chrome.scroll(x=0, y=500)

# 3. Tab Management
tabs = chrome.tabs                                            # List[Tab] handles
active_tab = chrome.active_tab
new_tab = chrome.new_tab("https://news.ycombinator.com")
new_tab.activate()
new_tab.close()

# 4. Synchronization
chrome.wait_for("[#12]", timeout=10.0, state="visible")
chrome.wait_for_url(r"github\.com/dashboard")

# 5. Extraction & Scripting
text = chrome.get_text("[#3]")
href = chrome.get_attribute("[#3]", "href")
eval_val = chrome.eval_js("window.innerWidth")
screenshot = chrome.screenshot()
```

---

## 📄 License

MIT
