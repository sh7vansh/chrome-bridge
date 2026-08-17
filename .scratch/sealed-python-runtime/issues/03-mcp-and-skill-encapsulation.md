# 03 — MCP Server Instructions & Skill Documentation Encapsulation

**What to build:**
Configure `mcp_server.py` as the canonical MCP server entry point and ensure all instructions, tool schemas, docstrings, and skill documentation ([skills/chrome-bridge/SKILL.md](../../skills/chrome-bridge/SKILL.md)) exclusively teach procedural Python automation workflows with zero reference to browser extensions, native messaging, or sockets.

**Blocked by:** 02 — REPL Engine Traceback Scrubbing

**Status:** ready-for-agent

- [x] `mcp_server.py` instructions and `execute_python` tool description emphasize procedural Python workflows (`chrome.snapshot()`, `chrome.click()`, loops, Ref-ID inspection) and state persistence.
- [x] `skills/chrome-bridge/SKILL.md` is reviewed and updated to ensure pristine Python REPL framing with zero leakage of extension mechanics.
- [x] `CONTEXT.md` is updated to reflect strict domain terminology boundaries.
- [x] `mcp-server.mjs` is documented as an internal testing fixture rather than an agent-facing server.
