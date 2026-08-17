# Research 06: MCP Server Tool Specification & Configuration Blueprint

**Ticket**: `06-mcp-server-tool-spec-and-config.md`  
**Status**: Completed  
**Type**: Task  
**Domain**: Model Context Protocol (MCP), Python Server, Tool Schemas, Client Configuration, Deployment  

---

## 1. Executive Summary

The transition from a multi-tool JSON-RPC wrapper (10+ individual tools like `chrome_click`, `chrome_type`, `chrome_scroll`) to a **Unified Persistent Python REPL Tool** (`execute_python`) dramatically simplifies the AI driver's tool space:
- Exposes exactly **one tool**: `execute_python(code)`.
- Eliminates multi-tool schema overhead and hallucinated argument types.
- Provides a persistent in-process session where variables, subroutines, and state persist across conversational turns.
- Connects directly to the Chrome extension background worker via the `/tmp/chrome_bridge.sock` native IPC socket.

---

## 2. Tool Schema & FastMCP Specification

### 2.1 Tool Definition: `execute_python`

```json
{
  "name": "execute_python",
  "description": "Execute Python code in a stateful, persistent runtime environment with procedural control over Google Chrome. Variables, helper functions, and imported modules persist across calls.\n\nUse the synchronous 'chrome' standard library to control open tabs, inspect distilled Semantic DOM snapshots, click elements, fill forms, and evaluate pages.\n\nKey APIs:\n- chrome.snapshot() -> Get compressed Semantic DOM outline with [#N] Ref-IDs\n- chrome.click(target) -> Click Ref-ID (e.g. 14 or '[#14]') or CSS selector\n- chrome.type(target, text, clear=True, press_enter=False) -> Type into element\n- chrome.navigate(url) -> Navigate active tab\n- chrome.tabs -> List all open tabs (<Tab id=... title=... active=...>)\n- chrome.tab(tab_id) -> Target specific tab handle\n- chrome.wait_for(target, timeout=10.0) -> Synchronously wait for element",
  "inputSchema": {
    "type": "object",
    "properties": {
      "code": {
        "type": "string",
        "description": "Python source code to execute in the persistent session."
      }
    },
    "required": ["code"]
  }
}
```

---

## 3. Server Implementation: `mcp-server.py`

```python
#!/usr/bin/env python3
"""Antigravity Chrome Bridge - FastMCP Server

Persistent Python REPL Runtime for AI Browser Automation.
"""

import sys
from mcp.server.fastmcp import FastMCP
from repl_engine import PythonReplSession

# Initialize FastMCP Server
mcp = FastMCP(
    "chrome-bridge",
    instructions=(
        "You have full procedural control over the user's active Google Chrome"
        " browser via the 'execute_python' tool.\n"
        "Always start by calling `chrome.snapshot()` to inspect the current"
        " page's interactive elements and Ref-IDs (`[#1]`, `[#2]`).\n"
        "Use `chrome.click(ref)` and `chrome.type(ref, text)` to interact"
        " directly with elements by their Ref-ID."
    ),
)

# Persistent in-memory session engine
_SESSION = PythonReplSession()


@mcp.tool(name="execute_python")
def execute_python(code: str) -> str:
  """Execute Python code in a persistent browser automation session.

  Args:
      code: Python code string to execute.

  Returns:
      Formatted tagged output with [stdout], [result], or [error] diagnostics.
  """
  return _SESSION.execute(code)


if __name__ == "__main__":
  mcp.run(transport="stdio")
```

---

## 4. AI Client Configuration Formats

### 4.1 Antigravity / Gemini CLI (`~/.agent/mcp_config.json` or project `mcp_config.json`)
```json
{
  "mcpServers": {
    "chrome-bridge": {
      "command": "python3",
      "args": [
        "/absolute/path/to/antigravity-chrome-bridge/mcp-server.py"
      ]
    }
  }
}
```

### 4.2 Claude Desktop (`claude_desktop_config.json`)
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "chrome-bridge": {
      "command": "python3",
      "args": [
        "/absolute/path/to/antigravity-chrome-bridge/mcp-server.py"
      ]
    }
  }
}
```

### 4.3 Cursor / Roo / Cline / Zed
```json
{
  "mcpServers": {
    "chrome-bridge": {
      "command": "python3",
      "args": [
        "${workspaceFolder}/mcp-server.py"
      ]
    }
  }
}
```

---

## 5. Dependencies & Packaging

### 5.1 `requirements.txt`
```text
mcp>=1.0.0
```

### 5.2 `pyproject.toml`
```toml
[project]
name = "antigravity-chrome-bridge"
version = "2.0.0"
description = "Persistent Python REPL Runtime and Native Messaging Bridge for Google Chrome"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.0.0",
]

[project.scripts]
chrome-bridge-mcp = "mcp_server:main"
```

---

## 6. Setup Script Migration: `setup.sh` / `setup-host.mjs`

The setup script updates:
1. Installs Native Messaging Host manifest for Chrome, Chromium, and Brave.
2. Checks Python 3.10+ and installs `mcp>=1.0.0` (using `pip install -e .` or `pip install -r requirements.txt`).
3. Injects `execute_python` server config into `~/.agent/mcp_config.json` and Claude Desktop configs.
4. Copies `SKILL.md` into `~/.agent/skills/chrome-bridge/SKILL.md`.
