# Spec: Adaptive & Context-Aware Chrome Bridge Architecture

**Label:** `ready-for-agent`  
**Parent Map:** [Map: Adaptive & Context-Aware Chrome Bridge Architecture](file:///home/shivansh/chrome-bridge/issues/map.md)

---

## Problem Statement

When controlling and automating a live Google Chrome browser session via autonomous AI coding agents:
1. **Cold-Start Latency (~20–30s):** Spawning a completely fresh subagent for every conversational turn forces the agent to re-read skills, discover SDK paths, and re-establish IPC connections repeatedly, ruining real-time user experience.
2. **Context Bloat & Token Degradation:** If a worker subagent is left running indefinitely without bounds, accumulated DOM trees, screenshots, and REPL traces bloat the LLM context window, triggering high token costs and degraded inference accuracy.
3. **Conversational Pronoun & State Loss:** Spawning fresh, blind subagents destroys conversational continuity. When a user issues follow-up commands like *"pause it"*, *"close this tab"*, or *"click the next one"*, the new worker lacks the active tab ID and prior page state, resulting in failed actions.
4. **Single-Page Application (SPA) DOM Click Fragility:** Attempting to click dynamic elements on SPAs (e.g., YouTube, YouTube Music, Spotify) before shadow-DOM hydration causes frequent element resolution errors and unnecessary retry cycles.

---

## Solution

An **Adaptive Lifecycle & Context-Aware Routing Architecture** that dynamically bifurcates incoming browser tasks:
- **Warm Route (`send_message`):** Keeps a lightweight subagent worker alive across consecutive conversational turns (up to 6 turns) with pre-imported SDK handles and established IPC channels, delivering instant `< 2s` execution.
- **Context-Budget Recycling:** Automatically retires and cleans up the worker after 6 turns or immediately following heavy, token-dense scraping operations.
- **Lean State Handover:** When spinning up a fresh worker, the parent agent pre-resolves pronouns and injects a deterministic 5-line markdown context header (`Active Tab ID`, `URL`, `Page Title`, `Media State`, `Resolved Intent`), enabling instant tab binding with zero DOM replay.
- **Native Media Fast-Paths:** First-class SDK media controller (`chrome.media.*`) that controls playback, volume, and track seeking directly via Shadow-DOM traversal and HTML5/MediaSession APIs in `< 5ms`, bypassing DOM parsing entirely.
- **Zero-Config SDK Bootstrap:** Pre-configured packaging and environment resolution so any subagent can immediately execute `from chrome_sdk import chrome` without path searching.

---

## User Stories

1. As an AI assistant user, I want my follow-up browser commands (like "pause it" or "skip 30 seconds") to execute in under 2 seconds, so that browser automation feels instant and responsive.
2. As an AI assistant user, I want the agent to remember which tab and video was playing when I say "pause it", so that I don't have to re-explain the URL or tab name.
3. As an AI agent orchestrator, I want to route consecutive browser actions to an existing warm subagent via persistent messaging, so that I eliminate cold-start re-imports and repeated skill reading.
4. As an AI agent orchestrator, I want to automatically recycle the worker subagent after 6 turns, so that accumulated DOM snapshots and outputs do not bloat the context window.
5. As an AI agent orchestrator, I want to spawn an isolated, fresh worker for heavy data scraping tasks, so that token-heavy tables do not pollute the primary warm conversation.
6. As a fresh subagent worker, I want to receive a clean 5-line context summary containing the active tab ID and current URL upon initialization, so that I can bind directly to the target tab without enumerating all browser tabs.
7. As a fresh subagent worker, I want the parent agent to pre-resolve conversational pronouns into unambiguous task intents, so that I never have to guess what "it" refers to.
8. As a subagent worker automating media SPAs (YouTube, Spotify), I want a dedicated `chrome.media.toggle()` method, so that I can toggle playback without searching for dynamic button Ref-IDs that mutate across route changes.
9. As a subagent worker, I want `chrome.media.status()` to query both HTML5 video elements and `navigator.mediaSession`, so that I can extract track title, artist, and playback state in a single call.
10. As a subagent worker, I want the media controller to penetrate nested shadow-DOM web components, so that custom player controls on YouTube Music or streaming apps respond reliably.
11. As a subagent worker, I want to execute relative seeking (e.g. `chrome.media.seek(15.0)`), so that I can fast-forward or rewind audio/video effortlessly.
12. As a subagent worker, I want to adjust volume via `chrome.media.set_volume(0.8)`, so that audio levels can be tuned programmatically.
13. As a developer installing Chrome Bridge, I want `pip install -e .` included in setup scripts, so that `chrome_sdk` is globally importable in the virtual environment regardless of working directory.
14. As an AI agent running Python scripts, I want the Chrome Bridge skill prompt to include an absolute path fallback preamble, so that import errors never occur if the environment is branched.
15. As an AI agent orchestrator, I want every worker completion response to return a lightweight telemetry block, so that the parent agent's session cache stays continuously updated without DOM parsing overhead.

---

## Implementation Decisions

### 1. Dual-Route Orchestration & Worker Recycling Protocol
- The parent agent manages a session memory tuple: `(active_worker_id, turn_count, cached_state)`.
- **Warm Route:** When `active_worker_id` exists and `turn_count < 6`, parent dispatches task prompts using `send_message`.
- **Recycle Trigger:** When `turn_count >= 6`, or when a task is classified as high-token/heavy-scraping, the parent calls `manage_subagents(Action="kill")`, resets `active_worker_id = None`, and spawns a fresh worker.
- **Fault Recovery:** If `send_message` fails, parent immediately kills the zombie subagent and initializes a fresh worker with `cached_state`.

### 2. Standardized Lean State Handover Schema
- Fresh subagents receive a standardized header in their prompt:
```markdown
### 🌐 Active Browser Context:
- **Active Tab ID:** <tab_id>
- **URL:** <current_url>
- **Page Title:** <page_title>
- **Media State:** <Playing|Paused|None> (<details>)
- **Resolved Intent:** <Explicit intent formulated by parent>
```
- Subagents bind directly to `chrome.get_tab(tab_id)` when `tab_id` is supplied.

### 3. Native Fast-Path Media Controller (`TabMedia`)
- Inlined prototype specification for native media control (derived from prototype):
```python
class TabMedia:
    def __init__(self, tab):
        self._tab = tab

    def status(self) -> dict: ...
    def toggle(self) -> dict: ...
    def play(self) -> dict: ...
    def pause(self) -> dict: ...
    def seek(self, seconds: float) -> dict: ...
    def set_volume(self, volume: float) -> dict: ...
```
- Integrated on `Tab` as `.media` property and on `Chrome` top-level client as `chrome.media.*`.
- Uses recursive shadow-DOM traversal script combined with `navigator.mediaSession` querying for zero-DOM-snapshot playback control.

### 4. Zero-Config Environment & Import Bootstrap
- `setup.sh` and `setup.ps1` execute editable install (`pip install -e .`).
- Skill prompt template incorporates an automated path injection preamble for universal import safety.
- `mcp_server.py` and `repl_engine.py` prepend their source directory to `sys.path` on startup.

---

## Testing Decisions

### Good Test Principles
- Tests must verify external behavior and API contracts without coupling to private internal variables.
- Mocking is strictly applied at the IPC client transport seam (`ChromeSocketClient.call`) or JavaScript evaluation seam (`eval_js`), validating that exact commands and arguments are dispatched and parsed.

### Tested Modules
- **`TabMedia` & `Chrome.media` API:** Test that `.toggle()`, `.play()`, `.pause()`, `.seek()`, `.set_volume()`, and `.status()` dispatch correct JS evaluation payloads and normalize return dictionaries.
- **Shadow-DOM JS Generation:** Verify that media queries properly escape inputs and bundle shadow root traversal.
- **State Handover & Context Serialization:** Test that context blocks are formatted and parsed without data loss.

### Prior Art
- `tests/test_chrome_sdk.py` (Tab action dispatch and polymorphic selector mocking).
- `tests/test_zero_leakage.py` (Clean lifecycle and isolation verification).

---

## Out of Scope

- Direct replacement of Native Messaging with raw Chrome DevTools Protocol (CDP) sockets.
- Multi-browser or multi-profile concurrent routing.
- Media downloading/recording streams.

---

## Further Notes

- All changes maintain full backward compatibility with existing `chrome.click()`, `chrome.snapshot()`, and Ref-ID selectors.
