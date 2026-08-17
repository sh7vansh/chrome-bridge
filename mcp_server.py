#!/usr/bin/env python3
"""Antigravity Chrome Bridge - Python MCP Server

Persistent Python REPL Runtime for AI Browser Automation.
"""

import sys
try:
    from mcp.server import MCPServer as FastMCP
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        from mcp.server.mcpserver import MCPServer as FastMCP

from repl_engine import PythonReplSession

# Initialize MCP Server
mcp = FastMCP(
    name="chrome-bridge",
    instructions=(
        "You have full procedural control over the user's active Google Chrome browser via the 'execute_python' tool.\n"
        "Always start by calling `chrome.snapshot()` to inspect the current page's interactive elements and Ref-IDs (`[#1]`, `[#2]`).\n"
        "Use `chrome.click(ref)` and `chrome.type(ref, text)` to interact directly with elements by their Ref-ID."
    ),
)

# Persistent in-memory session engine
_SESSION = PythonReplSession()


@mcp.tool(
    name="execute_python",
    description=(
        "Execute Python code in a persistent browser automation session. "
        "State, variables, imports, and functions persist across calls. "
        "The synchronous `chrome` module is pre-injected to control browser tabs, "
        "inspect DOM snapshots, and perform page actions."
    )
)
def execute_python(code: str) -> str:
    """Execute Python code in a persistent browser automation session.

    Args:
        code: Python source code string to execute.

    Returns:
        Formatted tagged output with [stdout], [result], or [error] diagnostics.
    """
    return _SESSION.execute(code)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
