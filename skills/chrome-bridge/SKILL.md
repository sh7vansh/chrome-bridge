---
name: chrome-bridge
description: Interact with the user's active Google Chrome browser via a stateful, persistent Python REPL runtime. Trigger when the user asks to inspect open tabs, read page content, navigate, click, fill forms, extract data, or automate multi-step workflows in their live browser.
---

# Chrome Bridge 2.0 (Python REPL Runtime)

Chrome Bridge provides a stateful, persistent in-memory **Python REPL** layer to control the user's active Google Chrome browser in real-time.

Instead of calling multiple disconnected tools, execute Python code via the single unified tool:
`execute_python(code)`

The synchronous standard library `chrome` is pre-injected into the session namespace. Variables, functions, and imports persist across conversational turns.

### Key API Reference

```python
# 1. Page Orientation & Snapshots (Distilled outline with [#N] Ref-IDs)
snapshot = chrome.snapshot()
print(snapshot)

# 2. Polymorphic Element Actions (Integer, Ref-ID string, or CSS selector)
chrome.click(14)                   # Integer Ref-ID
chrome.click("[#14]")              # Ref-ID token
chrome.type("[#2]", "query", clear=True, press_enter=True)
chrome.select("[#5]", "value")     # Dropdowns
chrome.hover("[#8]")

# 3. Tab Management & Navigation
tabs = chrome.tabs                 # List[Tab]
active = chrome.active_tab         # Tab handle
chrome.navigate("https://github.com")
tab = chrome.new_tab("https://news.ycombinator.com")
tab.activate()
tab.close()

# 4. Synchronization & Waiting
chrome.wait_for("[#10]", timeout=10.0, state="visible")
chrome.wait_for_url(r"github\.com/dashboard")

# 5. Extraction & Evaluation
text = chrome.get_text("[#3]")
attr = chrome.get_attribute("[#3]", "href")
val = chrome.eval_js("window.innerWidth")
screenshot_data = chrome.screenshot()
```

### Self-Healing & Diagnostics
When an element re-renders or changes Ref-ID, `ElementNotFoundError` automatically suggests candidate near-matches and attaches a fresh `[diagnostic_auto_snapshot]` in the response for instant single-turn recovery.
