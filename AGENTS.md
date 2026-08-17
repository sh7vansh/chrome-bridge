# AGENTS.md

Welcome to **Chrome Bridge** — a stateful, in-memory bridge between AI agents and a live Google Chrome browser via a Python REPL runtime.

## Core Rules & Intent Routing

### 1. Live Browser Automation (`chrome-bridge`)
- Whenever the user asks to inspect open tabs, read active pages, navigate, click, fill forms, extract data from their active browser session, or automate web workflows, **always activate the `chrome-bridge` skill**.
- **Do NOT fallback** to static HTTP fetch tools (`read_url_content`, `curl`) when interacting with the user's live browser, logged-in sessions, or multi-step web interactions.
- **Dynamic Execution Dispatch:**
  - **Inline (Main turn):** Simple queries, checking tabs/status, single-page snapshots, and 1–2 direct atomic actions.
  - **Dedicated Subagent (`chrome_worker`):** Multi-step workflows, pagination/scraping across multiple pages, cross-tab comparisons, or exploratory tasks with DOM retry loops to keep the main context clean.
- Interact with the browser using the synchronous `chrome` instance in `chrome_sdk.py` or the Python REPL runtime.

### 2. Python Runtime & Architecture
- **Runtime:** Python 3.11+ with dependencies in `requirements.txt` / `pyproject.toml`.
- **REPL Engine:** `repl_engine.py` maintains persistent session state across turns.
- **Native Host & Extension:** `native-host.mjs` handles Native Messaging to the Chrome extension in `extension/`.
- **MCP Server:** `mcp_server.py` exposes tools if operating over Model Context Protocol.

### 3. Testing & Verification
- Run tests test-first before and after modifications:
  ```bash
  pytest tests/
  # or
  ./test.sh
  ```
- Key test suites:
  - `tests/test_chrome_sdk.py`: SDK API surface and polymorphic selectors.
  - `tests/test_repl_engine.py`: Persistent variable state and execution sandbox.
  - `tests/test_diagnostics.py`: Self-healing Ref-ID recovery and candidate matches.
  - `tests/test_zero_leakage.py`: Cleanup and leak prevention.

### 4. Skills & Agent Guidelines
- Workspace skills reside under `.agents/skills/<skill-name>/SKILL.md`.
- Follow the guidelines in `.agents/skills/writing-for-agents/SKILL.md` when authoring or refining skill descriptions and context pointers.
