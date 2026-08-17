# 05 — FastMCP Server, Packaging, Setup Migration & Full Capability Test Suite

**What to build:** Replaces the legacy Node.js MCP server with `mcp-server.py` exposing the single `execute_python(code)` tool via FastMCP. Packages dependencies in `pyproject.toml` and `requirements.txt` (`mcp>=1.0.0`), updates setup scripts (`setup.sh` / `setup-host.mjs`) to configure client configurations (Antigravity CLI, Claude Desktop, Cursor, Zed), and establishes a comprehensive end-to-end integration test suite verifying full multi-step browser automation workflows over MCP stdio.

**Blocked by:** 04 — Single-Turn Self-Healing Diagnostics & Interceptor Detection.

**Status:** ready-for-agent

- [ ] `mcp-server.py` implements FastMCP server with instructions and the `execute_python(code: str) -> str` tool.
- [ ] Server initializes a single persistent `PythonReplSession` per client process.
- [ ] `pyproject.toml` and `requirements.txt` define project metadata and dependencies (`mcp>=1.0.0`).
- [ ] Setup script (`setup.sh` / `setup-host.mjs`) installs Native Host manifests and registers the Python MCP server in `~/.agent/mcp_config.json` and Claude Desktop configs.
- [ ] Comprehensive end-to-end integration test suite (`tests/test_full_capabilities.py`) executes 10+ browser actions (status, snapshot, click, type, multi-tab, scroll, wait, diagnostics) over stdio JSON-RPC.
- [ ] `README.md` and documentation updated to reflect Python REPL runtime commands and examples.
