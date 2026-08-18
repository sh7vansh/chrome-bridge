---
name: chrome-bridge
description: Control, inspect, and automate the user's live, active Google Chrome browser session via the stateful Python REPL runtime. MANDATORY whenever the user asks to view open tabs, read active pages, click, fill forms, navigate, extract browser data, or run browser workflows. Dynamically executes simple actions inline and delegates complex multi-step workflows to a dedicated chrome_worker subagent.
---

# Chrome Bridge (Python REPL Runtime & Dynamic Execution)

Chrome Bridge provides a stateful, persistent in-memory **Python REPL** layer to control the user's active Google Chrome browser in real-time.

---

## 🚦 Dual-Route Orchestration & Worker Lifecycle Protocol

To keep the parent conversation context clean and protect token limits from large DOM snapshots, **ALL browser tasks must be executed via a dedicated worker subagent.**

### 1. Warm Worker Reuse (`send_message`)
The parent agent tracks `(active_worker_id, turn_count, cached_state)` in its context:
- **Initial / Cold Turn:** Spawn a worker subagent with `invoke_subagent` and capture `conversationID`.
- **Continuation Turns (Turns 2–6):** Reuse the warm worker via `send_message(Recipient=active_worker_id, Message=...)` to eliminate cold-start re-imports and prompt bloat.
- **Recycle Trigger (Turn >= 6):** Retire the subagent via `manage_subagents(Action="kill", ConversationIds=[active_worker_id])`, reset `active_worker_id = None`, and spawn a fresh worker.
- **Heavy Workload Isolation:** High-token scraping or multi-page crawling tasks bypass the warm pool; spawn a dedicated fresh subagent and terminate it immediately after.
- **Fault Recovery:** If `send_message` errors or times out, immediately kill the worker and initialize a fresh subagent with `cached_state`.

### 2. Lean State Handover Schema
When spawning a fresh worker (or resetting workers post-recycle), inject the standardized 5-line markdown context header into the prompt:

```markdown
### 🌐 Active Browser Context:
- **Active Tab ID:** <tab_id>
- **URL:** <current_url>
- **Page Title:** <page_title>
- **Media State:** <Playing|Paused|None> (<details>)
- **Resolved Intent:** <Explicit intent formulated by parent>
```

- **Pronoun Pre-Resolution:** Parent agent resolves conversational pronouns (e.g. "pause it", "skip ahead", "close this tab") against cached state into explicit task intents before dispatching.
- **Direct Tab Binding:** Fresh workers bind directly to `tab = chrome.get_tab(tab_id)` (or fallback to `chrome.active_tab`).
- **Telemetry Return Block:** Every worker completion response returns lightweight telemetry to keep parent state updated:
  ```json
  {"tab_id": 12, "url": "https://music.youtube.com/...", "title": "Song Title", "media_playing": true}
  ```

---

## 🚀 Zero-Config SDK Bootstrap Preamble

Subagents and worker scripts execute with the standard import preamble:

```python
import sys, os, site, glob

for p in [os.getcwd(), os.path.expanduser("~/.chrome-bridge"), os.path.expanduser("~/chrome-bridge")]:
    if os.path.exists(os.path.join(p, "chrome_sdk.py")):
        if p not in sys.path:
            sys.path.insert(0, p)
        venv = os.path.join(p, ".venv")
        if os.path.isdir(venv):
            if sys.platform == "win32":
                sp = os.path.join(venv, "Lib", "site-packages")
                if os.path.isdir(sp):
                    site.addsitedir(sp)
            else:
                for sp in glob.glob(os.path.join(venv, "lib", "python*", "site-packages")):
                    if os.path.isdir(sp):
                        site.addsitedir(sp)
        break

from chrome_sdk import chrome
```


---

## 🛠️ Python API Reference

```python
import chrome_sdk
from chrome_sdk import chrome

# 1. Orientation & Snapshots
snapshot = chrome.snapshot()          # Formatted outline with [#N] Ref-IDs

# 2. Interactions (Ref-ID, Selector, or Accessible Name)
chrome.click("[#14]")                 # Ref-ID token, integer 14, or CSS selector
chrome.type("[#2]", "query", clear=True, press_enter=True)
chrome.select("[#5]", "value")        # Dropdowns
chrome.hover("[#8]")

# 3. Navigation & Tabs
tabs = chrome.tabs                    # List[Tab]
active = chrome.active_tab            # Active Tab handle
tab = chrome.get_tab(12)              # Scoped Tab handle by ID (or chrome.tab(12))
chrome.navigate("https://...")        # Navigate active tab
tab = chrome.new_tab("https://...")   # Open new tab

# 4. Native Fast-Paths & Media Controller (Zero-DOM-Snapshot)
media_info = chrome.media.status()    # Real-time state from HTML5 Video/Audio & MediaSession
chrome.media.toggle()                 # Fast play/pause toggle (penetrates shadow-DOM)
chrome.media.play()                   # Play active media
chrome.media.pause()                  # Pause active media
chrome.media.seek(15.0)               # Seek relative seconds (+15s or -10s)
chrome.media.set_volume(0.8)          # Set volume level (0.0 to 1.0)
# Tab-scoped media control:
# tab.media.toggle(), tab.media.status(), etc.

# 5. Synchronization & Waiting
chrome.wait_for("[#10]", timeout=10.0, state="visible")
chrome.wait_for_url(r"music\.youtube\.com/watch")

# 6. Extraction & JavaScript Evaluation
text = chrome.get_text("[#3]")
val = chrome.eval_js("(() => document.querySelector('video')?.paused)()")
screenshot_data = chrome.screenshot()

# 7. Self-Healing & Diagnostics
# When an element re-renders or changes Ref-ID, ElementNotFoundError automatically suggests
# candidate near-matches and attaches a fresh [diagnostic_auto_snapshot] for single-turn recovery.
```
