#!/usr/bin/env python3
"""Chrome Bridge - Python MCP Server

Persistent Python REPL Runtime for AI Browser Automation.
Equipped with full embedded SDK reference, MCP resources, and prompt templates
for seamless compatibility with standalone MCP clients (Claude Desktop, Cursor, Cline, etc.).
"""

import os
import sys

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from chrome_sdk import auto_bootstrap_environment
    auto_bootstrap_environment()
except ImportError:
    pass


try:
    from mcp.server import MCPServer as FastMCP
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        from mcp.server.mcpserver import MCPServer as FastMCP

from chrome_bridge.repl import PythonReplSession, ReplMetadataCatalog, ReplSessionEngine

API_DOCS = ReplMetadataCatalog.get_api_docs()
WORKFLOW_GUIDE = ReplMetadataCatalog.get_workflow_guide()
TOOL_DESCRIPTION = ReplMetadataCatalog.get_tool_description()

# Initialize MCP Server
mcp = FastMCP(
    name="chrome-bridge",
    instructions=ReplMetadataCatalog.get_server_instructions(),
)

# Persistent in-memory session engine with auto-ambient header orientation
_SESSION = PythonReplSession(include_ambient=True)


@mcp.tool(
    name="execute_python",
    description=ReplMetadataCatalog.get_tool_description()
)
def execute_python(code: str) -> str:
    """Execute Python code in a persistent browser automation session.

    Args:
        code: Python source code string to execute.

    Returns:
        Formatted tagged output with [stdout], [result], or [error] diagnostics.
    """
    return _SESSION.execute(code)


# MCP Resources for clients that inspect documentation
try:
    @mcp.resource("chrome-bridge://docs/api")
    def get_api_docs() -> str:
        """Complete Chrome Bridge Python SDK API Reference."""
        return ReplMetadataCatalog.get_api_docs()

    @mcp.resource("chrome-bridge://docs/workflow")
    def get_workflow_guide() -> str:
        """Chrome Bridge Workflow Guide, Patterns, and Security Practices."""
        return ReplMetadataCatalog.get_workflow_guide()
except Exception:
    pass


# MCP Prompts for interactive client workflows
try:
    @mcp.prompt()
    def browser_automation(goal: str = "") -> str:
        """Guide the model through executing a complete browser automation task."""
        return ReplMetadataCatalog.get_browser_automation_prompt(goal=goal)

    @mcp.prompt()
    def media_control(action: str = "status") -> str:
        """Quick prompt to inspect or control browser media playback."""
        return ReplMetadataCatalog.get_media_control_prompt(action=action)
except Exception:
    pass


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

