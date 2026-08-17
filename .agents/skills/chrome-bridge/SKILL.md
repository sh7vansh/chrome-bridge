---
name: chrome-bridge
description: Control, inspect, and automate the user's live, active Google Chrome browser session via the stateful Python REPL runtime. MANDATORY whenever the user asks to view open tabs, read active pages, click, fill forms, navigate, extract browser data, or run browser workflows. Dynamically executes simple actions inline and delegates complex multi-step workflows to a dedicated chrome_worker subagent.
---

# Chrome Bridge (Python REPL Runtime & Dynamic Execution)

Chrome Bridge provides a stateful, persistent in-memory **Python REPL** layer to control the user's active Google Chrome browser in real-time.

---

## 🚦 Execution Protocol: Always Delegate to Subagent

To keep the parent conversation context clean and protect token limits from large DOM snapshots, **ALL browser tasks must be immediately delegated to a `self` subagent.**

Do NOT execute browser interactions inline in the parent context.

```python
invoke_subagent(Subagents=[{
    "TypeName": "self",
    "Role": "Browser Automation Worker",
    "Prompt": """Execute the following browser task using the active `chrome-bridge` skill:
[Insert User Request]

Execution Guidelines:
1. Use `execute_python` (or fallback to `from chrome_sdk import chrome`).
2. Write the entire sequence in 1 end-to-end Python execution (navigate -> wait_for -> click -> verify).
3. Verify the final page/player state before finishing.
4. Return a concise markdown summary to the parent agent. Do NOT dump raw DOM trees."""
}])
```

---

## 🛠️ Python API Reference (Inherited by Worker)

```python
import chrome_sdk
chrome = chrome_sdk.chrome

# 1. Orientation & Snapshots
snapshot = chrome.snapshot()          # Formatted outline with [#N] Ref-IDs

# 2. Interactions (Ref-ID, Selector, or Accessible Name)
chrome.click("[#14]")                 # Ref-ID token, integer 14, or CSS selector
chrome.type("[#2]", "query", clear=True, press_enter=True)
chrome.select("[#5]", "value")        # Dropdowns
chrome.hover("[#8]")

# 3. Navigation & Tabs
tabs = chrome.tabs                    # List[Tab]
active = chrome.active_tab            # Tab handle
chrome.navigate("https://...")        # Navigate active tab
tab = chrome.new_tab("https://...")   # Open new tab

# 4. Synchronization & Waiting
chrome.wait_for("[#10]", timeout=10.0, state="visible")
chrome.wait_for_url(r"music\.youtube\.com/watch")

# 5. Extraction & JavaScript Evaluation
text = chrome.get_text("[#3]")
val = chrome.eval_js("(() => document.querySelector('video')?.paused)()")
screenshot_data = chrome.screenshot()
# 6. Self-Healing & Diagnostics
# When an element re-renders or changes Ref-ID, ElementNotFoundError automatically suggests
# candidate near-matches and attaches a fresh [diagnostic_auto_snapshot] for single-turn recovery.
```
