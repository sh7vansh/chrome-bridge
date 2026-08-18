# AGENTS.md

Welcome to **Chrome Bridge** — a stateful, in-memory bridge between AI agents and a live Google Chrome browser via a Python REPL runtime.

## Core Rules & Intent Routing

### 1. Live Browser Automation (`chrome-bridge`)
- Whenever the user asks to inspect open tabs, read active pages, navigate, click, fill forms, extract data from their active browser session, or automate web workflows, **always activate the `chrome-bridge` skill**.
- **Do NOT fallback** to static HTTP fetch tools (`read_url_content`, `curl`) when interacting with the user's live browser, logged-in sessions, or multi-step web interactions.
- **Execution Delegation & Warm-Worker Pooling:**
  - Delegate browser automation to a `self` subagent (`TypeName="self"`, `Role="Browser Automation Worker"`).
  - Track `(active_worker_id, turn_count, cached_state)`: reuse warm workers across turns 2–6 via `send_message` to achieve < 2s response latency.
  - Automatically recycle workers after 6 turns or immediately following heavy scraping workloads using `manage_subagents(Action="kill")`.
  - When spawning fresh workers, inject the standardized 5-line markdown context header (`Active Tab ID`, `URL`, `Page Title`, `Media State`, `Resolved Intent`) and pre-resolve conversational pronouns.
- Always execute browser actions via the **`execute_python`** MCP tool (from the `chrome-bridge` server) or `from chrome_sdk import chrome`. Use native fast-paths (`chrome.media.*`) for multimedia and SPAs to avoid unnecessary DOM snapshots.

### 2. Python Runtime & Architecture
- **Runtime:** Python 3.10+ with dependencies in `requirements.txt` / `pyproject.toml`.
- **REPL Engine:** `repl_engine.py` maintains persistent session state across turns with auto-injected `sys.path`.
- **SDK & Fast-Paths:** `chrome_sdk.py` exposes synchronous client, `Tab`, `Chrome`, and `TabMedia` controller.
- **Native Host & Extension:** `native_host.py` handles Native Messaging to the Chrome extension in `extension/`.
- **MCP Server:** `mcp_server.py` exposes tools over Model Context Protocol with auto-injected `sys.path`.

### 3. Testing & Verification
- Run tests test-first before and after modifications:
  ```bash
  pytest tests/
  # or
  ./test.sh
  ```
- Key test suites:
  - `tests/test_chrome_sdk.py`: SDK API surface and polymorphic selectors.
  - `tests/test_media_fastpath.py`: `TabMedia` and native multimedia fast-paths.
  - `tests/test_repl_engine.py`: Persistent variable state and execution sandbox.
  - `tests/test_diagnostics.py`: Self-healing Ref-ID recovery and candidate matches.
  - `tests/test_zero_leakage.py`: Cleanup and leak prevention.

### 4. Skills & Agent Guidelines
- Workspace skills reside under `.agents/skills/<skill-name>/SKILL.md`.
- Follow the guidelines in `.agents/skills/writing-for-agents/SKILL.md` when authoring or refining skill descriptions and context pointers.
