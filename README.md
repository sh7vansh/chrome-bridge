# Chrome Bridge 2.0 (Persistent Python REPL Runtime)

A high-performance Model Context Protocol (MCP) server and Chrome Extension providing a **stateful, persistent in-memory Python REPL runtime** to control and inspect your active Google Chrome browser in real-time.

Instead of orchestrating dozens of discrete tools across multiple latency-heavy round-trips, AI agents (Antigravity, Claude Desktop, Cursor, Gemini) execute procedural Python scripts via a single unified MCP tool: **`execute_python(code)`**.

---

## 🌟 Key Features

- **Persistent Python REPL Session**: Variables, functions, imports, and dataframes defined in turn 1 persist seamlessly into subsequent turns.
- **Token-Distilled Semantic DOM Snapshots**: In-page `TreeWalker` traversal with AccName 1.2 name computation and visibility filtering delivers **99%+ token reduction** over raw DOM trees.
- **Lightweight Indexed Ref-IDs**: Actionable elements receive 1-based sequential Ref-IDs (`[#1]`, `[#2]`), eliminating brittle selectors and coordinate hallucination.
- **Polymorphic Locator Dispatch**: SDK methods accept integer Ref-IDs (`14`), token strings (`"[#14]"` / `"#14"`), or standard CSS selectors (`"button.submit"`).
- **Dual-Layer Token Budgeting**: Structural collection pruning (10 items, 10 keys, depth 3) + hard 12,000-character safety cap with head-and-tail preservation (`... [N chars / M tokens omitted] ...`).
- **Single-Turn Self-Healing Diagnostics**:
  - Auto-injected `[diagnostic_auto_snapshot]` on unhandled browser exceptions.
  - Fuzzy near-match candidate suggestions for stale Ref-IDs (`Did you mean: [#18] (button 'Submit')?`).
  - Coordinate hit-testing with interceptor detection (modals, overlays, cookie banners).
  - Synchronous waiting helpers with rich timeout state introspection (`readyState`, DOM visibility).
- **Everyday Profile**: Works with your regular Chrome profile (passwords, logins, cookies intact) via Native Messaging without requiring debug flags.

---

## 📦 Quick Start & Installation

### 1. Run Setup
```bash
git clone https://github.com/sh7vansh/chrome-bridge.git
cd chrome-bridge
./setup.sh
```
> **What `./setup.sh` does:**
> - Initializes Python virtualenv with `mcp>=1.0.0` and `pytest`.
> - Registers the Native Messaging Host in Google Chrome, Chromium, and Brave.
> - Auto-registers the MCP Server in `~/.agent/mcp_config.json` and Claude Desktop configs.
> - Copies the agent skill to `~/.agent/skills/chrome-bridge/SKILL.md`.

### 2. Load the Chrome Extension
1. Open Google Chrome and go to `chrome://extensions`.
2. Enable **Developer mode** (toggle in top right).
3. Click **Load unpacked** and select the `chrome-bridge/extension` directory.
4. The extension icon will appear in your toolbar showing **`🟢 Native Bridge`**.

### 3. Verification
Run the automated test suite anytime:
```bash
.venv/bin/pytest
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
