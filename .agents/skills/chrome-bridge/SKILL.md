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

### 1. Inline Execution (Simple / Quick Tasks)
Execute inline in the current turn using `run_command` with `python3 -c "..."` or persistent REPL:
- **Inspect open tabs:** `chrome.tabs`, `chrome.active_tab`
- **Single atomic action:** Navigate to URL, click a known button, enter text in a single field
- **Quick extraction:** Fetching active page snapshot or single element text/attribute

### 2. Dedicated Subagent (`chrome_worker` for Complex Workflows)
For multi-step flows, deep scraping across pages, or multi-tab tasks, invoke (or define) a dedicated `chrome_worker` subagent so that detailed DOM interactions, snapshots, and error-recovery loops do not clutter the parent context.

#### Defining `chrome_worker` (if not already defined):
```python
define_subagent(
    name="chrome_worker",
    description="Autonomous browser agent for executing multi-step workflows, paginated extractions, and interactive web tasks via Chrome Bridge.",
    system_prompt="""You are a dedicated Chrome Browser Automation Worker.
You interact with the user's live Google Chrome browser via `chrome_sdk` in Python.
Rules:
1. Always import `chrome_sdk` and use `chrome = chrome_sdk.chrome`.
2. Take compact snapshots (`chrome.snapshot()`) to locate element Ref-IDs before interacting.
3. Perform the requested multi-step workflow autonomously, handling element waits and retries.
4. When finished, synthesize the findings/results into a clean, structured summary and return it to the parent agent. Do not dump raw HTML or large DOM snapshots in your final response.
""",
    enable_write_tools=True
)
```

#### Invoking `chrome_worker`:
```python
invoke_subagent(Subagents=[{
    "TypeName": "chrome_worker",
    "Role": "Browser Automation Worker",
    "Prompt": "Navigate to the search results, paginate through the first 3 pages, extract product names and prices into a markdown table, and report back."
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
