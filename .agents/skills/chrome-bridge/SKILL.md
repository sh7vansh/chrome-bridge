---
name: chrome-bridge
description: Control, inspect, and automate the user's live, active Google Chrome browser session via the stateful Python REPL runtime. MANDATORY whenever the user asks to view open tabs, read active pages, click, fill forms, navigate, extract browser data, or run browser workflows. Dynamically executes simple actions inline and delegates complex multi-step workflows to a dedicated chrome_worker subagent.
---

# Chrome Bridge (Python REPL Runtime & Dynamic Execution)

Chrome Bridge provides a stateful, persistent in-memory **Python REPL** layer to control the user's active Google Chrome browser in real-time.

---

## 🚦 Dynamic Execution Routing

Choose dynamically between **Inline Execution** and a **Dedicated Subagent** based on task complexity:

```
                      ┌────────────────────────────────────────┐
                      │          Incoming Browser Task         │
                      └───────────────────┬────────────────────┘
                                          │
                        Is it a simple 1–2 action call?
                                          │
                         ┌────────────────┴────────────────┐
                         ▼                                 ▼
               [Inline Execution]              [Dedicated Subagent]
               - Inspect tabs/status           - Multi-step workflows
               - Single page snapshot          - Multi-page pagination / scraping
               - 1–2 direct actions            - Multi-tab comparisons
               - Quick read/evaluation         - DOM retry & exploration loops
```

### 1. Cross-Platform Execution
Run Python code via the persistent REPL or resolved executable:
- **Linux/macOS:** `.venv/bin/python -c "..."` or `python3 repl_engine.py -c "..."`
- **Windows:** `.venv\Scripts\python.exe -c "..."` or `py -3 repl_engine.py -c "..."`

---

### 2. Dedicated Subagent (`chrome_worker`)
For complex or multi-step workflows, spawn `chrome_worker` to keep parent context clean:

```python
define_subagent(
    name="chrome_worker",
    description="Dedicated subagent to execute browser automation workflows via Chrome Bridge.",
    system_prompt="""Control the live Chrome browser via Python `chrome_sdk`.
- Execute via `.venv/bin/python` (Linux/macOS) or `.venv\\Scripts\\python.exe` (Windows), or `python repl_engine.py -c "..."`.
- Always import `chrome_sdk` and use `chrome = chrome_sdk.chrome`.
- Use `chrome.snapshot()` to get [#N] element Ref-IDs, perform actions, and wait for navigation.
- Return a concise, structured markdown report. Do not dump raw HTML or large DOM snapshots.""",
    enable_write_tools=True
)

invoke_subagent(Subagents=[{
    "TypeName": "chrome_worker",
    "Role": "Browser Worker",
    "Prompt": "Navigate to the site, extract the table data, and report back."
}])
```

---

## 🛠️ Key API Reference

```python
import chrome_sdk
chrome = chrome_sdk.chrome

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
