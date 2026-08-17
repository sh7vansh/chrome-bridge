Type: task
Status: closed
Assignee: antigravity
Blocked by: 03, 04, 05

## Question

What is the exact specification for `mcp-server.py`, its `execute_python` tool schema, configuration files for AI clients, and setup script migration?

## Findings

Specification, FastMCP tool definition, packaging configuration, and client schemas completed in [06-mcp-server-tool-spec-and-config.md](../research/06-mcp-server-tool-spec-and-config.md).

Key deliverables:
1. **Unified Tool**: Single `execute_python(code: str) -> str` tool replacing 10+ granular JSON-RPC tools.
2. **Server Implementation**: `mcp-server.py` wrapping persistent `PythonReplSession`.
3. **Client Configuration Formats**: JSON configurations documented for Antigravity CLI, Claude Desktop, Cursor, and Zed.
4. **Packaging & Dependencies**: `requirements.txt` (`mcp>=1.0.0`) and `pyproject.toml`.

