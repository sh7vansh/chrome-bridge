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

### 1. Cross-Platform Python Execution

To reliably run Python code across Linux, macOS, and Windows (avoiding path and encoding issues):

```bash
# Linux / macOS:
PYTHON_EXEC="$([ -f ".venv/bin/python" ] && echo ".venv/bin/python" || which python3 || echo "python")"
PYTHONIOENCODING=utf-8 $PYTHON_EXEC -c "import chrome_sdk; chrome = chrome_sdk.chrome; print(chrome.snapshot())"

# Windows (Command Prompt / PowerShell):
# PowerShell / CMD: Use .venv\Scripts\python.exe or py -3
$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"
.venv\Scripts\python.exe -c "import chrome_sdk; chrome = chrome_sdk.chrome; print(chrome.snapshot())"

# Or run via the built-in REPL runner:
$PYTHON_EXEC repl_engine.py -c "print(chrome.tabs)"
```

For multi-step logic, write a temporary Python script to a file (e.g. `.scratch/automate.py`) and run it with the resolved Python executable.

---

### 2. Dedicated Subagent (`chrome_worker` for Complex Workflows)

When complex browser tasks (scraping, multi-page flows, pagination, deep form fills) are requested, spawn the dedicated `chrome_worker` with **high reasoning model** (`Model: "inherit"` or `"pro"`):

#### Defining `chrome_worker` (if not already defined):
```python
define_subagent(
    name="chrome_worker",
    description="Autonomous high-reasoning browser automation worker that controls Chrome Bridge, handles DOM navigation, self-heals stale element refs, and reports synthesized findings.",
    system_prompt="""You are a dedicated Chrome Browser Automation Worker.
You interact with the user's active Google Chrome browser via `chrome_sdk` in Python.

### Cross-Platform Execution Rule:
- Locate the Python executable:
  - Linux/macOS: Prefer `.venv/bin/python` if present, else `python3` or `python`.
  - Windows: Prefer `.venv\\Scripts\\python.exe` if present, else `py -3` or `python`.
- For multi-line tasks, write your automation code to `.scratch/automate.py` and run it with the resolved Python executable.
- Always ensure `import chrome_sdk; chrome = chrome_sdk.chrome`.

### 5-Step Autonomous Browsing Playbook:
1. **ORIENT**: Check `chrome.active_tab.url` and print `chrome.snapshot()`. Read element Ref-IDs (`[#N]`). Never hallucinate IDs.
2. **PLAN & ACT**: Perform precise actions (`chrome.click(14)`, `chrome.type('[#2]', 'query', press_enter=True)`, `chrome.select`, `chrome.scroll`).
3. **SYNCHRONIZE**: After actions that trigger navigation or AJAX rendering, call `chrome.wait_for('[#N]', timeout=10)` or `chrome.wait_for_url(...)` or `time.sleep(1)` before taking the next snapshot.
4. **SELF-HEAL**: If `ElementNotFoundError` occurs, read the suggested candidate matches or take a fresh `chrome.snapshot()` to get updated Ref-IDs. Retry up to 3 times with the updated selector.
5. **SYNTHESIZE**: When finished, return a clean, structured Markdown summary (tables, bullet points, links, exact data extracted) back to the parent agent. Do not dump raw HTML or huge DOM snapshots in your final response.
""",
    enable_write_tools=True
)
```

#### Invoking `chrome_worker`:
```python
invoke_subagent(Subagents=[{
    "TypeName": "chrome_worker",
    "Role": "Browser Automation Worker",
    "Model": "inherit",
    "Prompt": "Navigate to the site, paginate through the first 3 pages, extract the product names and prices into a markdown table, and report back."
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
