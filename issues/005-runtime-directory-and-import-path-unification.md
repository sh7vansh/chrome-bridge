# 005 — Runtime Directory Standardization & Multi-Path SDK Bootstrap

**Parent:** [Map: Adaptive & Context-Aware Chrome Bridge Architecture](file:///home/shivansh/chrome-bridge/issues/map.md)

**What to build:**
Standardize the canonical persistent runtime installation directory to `~/.chrome-bridge` and implement dynamic multi-directory candidate fallback (`os.getcwd()`, `~/.chrome-bridge`, `~/chrome-bridge`) across the SDK, subagent prompt preamble in `SKILL.md`, and MCP servers, ensuring subagents never throw `ModuleNotFoundError: No module named 'chrome_sdk'`.

## Acceptance criteria

- [x] `setup-host.mjs` consistently defaults `INSTALL_DIR` to `~/.chrome-bridge` for persistent installs and synchronizes runtime files.
- [x] `.agents/skills/chrome-bridge/SKILL.md` SDK bootstrap preamble includes multi-directory probing (`os.getcwd()`, `~/.chrome-bridge`, `~/chrome-bridge`).
- [x] `chrome_sdk.py`, `repl_engine.py`, and `mcp_server.py` auto-resolve and prepend the runtime directory to `sys.path`.
- [x] Automated tests verify SDK import succeeds under various working directory configurations.

## Blocked by

- None — can start immediately.

**Status:** closed

