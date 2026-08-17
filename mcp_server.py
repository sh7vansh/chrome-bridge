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
        "You have full procedural control over the user's active Google Chrome browser via the 'execute_python' tool.\n\n"
        "ENVIRONMENT CAPABILITIES:\n"
        "- Persistent Python REPL: Variables, imports, helper functions, and state persist across successive calls.\n"
        "- Injected SDK: The synchronous `chrome` module is pre-injected and ready to use.\n\n"
        "RECOMMENDED WORKFLOW:\n"
        "1. Orientation: Always inspect the page with `print(chrome.snapshot())` to obtain the Semantic DOM outline and element Ref-IDs (`[#1]`, `[#2]`).\n"
        "2. Targeted Actions: Interact polymorphically using Ref-IDs or selectors, e.g. `chrome.click(14)`, `chrome.type('[#2]', 'search query', press_enter=True)`.\n"
        "3. Multi-Step Subroutines: Write complete loops and workflows (form fills, pagination, data extraction) in a single script for high throughput.\n"
        "4. Synchronization: Use `chrome.wait_for('[#5]')` and `chrome.wait_for_url(r'...')` to handle dynamic page changes.\n"
        "5. Self-Healing: If an element is not found, inspect the automatic `[diagnostic_auto_snapshot]` or fuzzy match suggestions in the error payload."
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
