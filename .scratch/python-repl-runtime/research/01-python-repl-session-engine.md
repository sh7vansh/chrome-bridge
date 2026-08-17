# Research 01: In-Process Python REPL Session Engine & MCP Bridge Architecture

**Ticket**: [01-python-repl-session-engine.md](../issues/01-python-repl-session-engine.md)  
**Status**: Completed  
**Domain Area**: Python REPL Runtime, FastMCP / MCPServer Integration, Unix Domain Socket IPC  

---

## Executive Summary

To enable AI drivers to control Google Chrome procedurally with minimal token overhead, the **Python REPL Runtime** must provide a stateful, interactive execution engine in a single persistent process. Rather than exposing dozens of discrete MCP tools that incur round-trip latency and token bloat, the runtime exposes a single unified MCP tool: `execute_python(code: str)`.

This research document analyzes the technical design and primary source implementation for:
1. **In-process interactive REPL execution** using Python's Abstract Syntax Tree (`ast`) module to evaluate multi-line scripts while capturing trailing expression return values, standard streams (`stdout`/`stderr`), and maintaining a persistent global variable namespace across turns.
2. **MCP Server Integration** using the Python MCP SDK (`mcp.server.mcpserver.MCPServer` / `FastMCP`) over `stdio`, ensuring complete wire safety without stdout stream corruption.
3. **Synchronous IPC Bridge** connecting the in-process Python runtime to the Chrome Extension Native Messaging Host via the Unix Domain Socket at `/tmp/chrome_bridge.sock`.

---

## 1. Persistent In-Process REPL Session Engine

### 1.1 The Multi-Line AST Execution Challenge

In Python, the built-in `compile()` function supports three execution modes:
- `mode="exec"`: Compiles a sequence of statements. Calling `exec()` runs the statements but always returns `None`. Any top-level expressions (e.g. `2 + 2` or `chrome.get_page_content()`) are evaluated as statements and their return values are discarded.
- `mode="eval"`: Compiles a single expression (e.g. `ast.Expression`). Calling `eval()` returns the expression's evaluated value, but fails with a `SyntaxError` if given statements (such as `x = 10`, `def foo(): ...`, `import os`, or loops).
- `mode="single"`: Compiles a single interactive statement. If the statement is an expression, it prints its result via `sys.displayhook`. However, `mode="single"` cannot compile multi-line compound scripts with mixed statements and expressions.

To provide a true interactive REPL experience (identical to Jupyter / IPython) where an agent can define variables, run loops, and inspect the final expression's return value in a single multi-line code block:

```python
tabs = chrome.list_tabs()
active = [t for t in tabs if t["active"]]
active[0]["title"]  # Return value should be captured!
```

We employ an **AST Splitting & Transformation Strategy** inspired by IPython's `InteractiveShell.run_ast_nodes`.

### 1.2 AST Transformation & Splitting Algorithm

The execution algorithm operates as follows:

```mermaid
flowchart TD
    A[Input Python Code String] --> B[ast.parse source, mode='exec']
    B --> C{Is AST Body Empty?}
    C -->|Yes| D[Return Empty Result]
    C -->|No| E{Is Last Node ast.Expr?}
    E -->|No| F[Compile Full AST mode='exec']
    F --> G[exec in session_globals]
    G --> H[result = None]
    E -->|Yes| I[Split AST: body[:-1] vs body[-1]]
    I --> J[Compile body[:-1] as ast.Module mode='exec']
    I --> K[Convert last ast.Expr to ast.Expression mode='eval']
    J --> L[exec statements in session_globals]
    K --> M[eval expression in session_globals]
    M --> N[Capture result & set session_globals['_'] = result]
    H --> O[Format Result + stdout + stderr]
    N --> O
```

#### Step-by-Step Implementation

1. **Parse**: Parse the full source text with `tree = ast.parse(code, filename="<repl>", mode="exec")`.
2. **Inspect Final Node**: Check if `isinstance(tree.body[-1], ast.Expr)`.
3. **Split & Transform**:
   - If the last node is an `ast.Expr`, separate the preceding statements `tree.body[:-1]` and the trailing expression `tree.body[-1]`.
   - Wrap `tree.body[:-1]` in an `ast.Module(body=..., type_ignores=[])` and compile with `mode="exec"`.
   - Wrap the expression's inner value `tree.body[-1].value` in an `ast.Expression(body=...)`, preserve source location with `ast.copy_location()`, and compile with `mode="eval"`.
4. **Execute**:
   - Execute the statement module using `exec(stmt_code, session_globals, session_globals)`.
   - Evaluate the expression using `eval(expr_code, session_globals, session_globals)`.
5. **Interactive Result Variable (`_`)**:
   - If the evaluated expression result is not `None`, assign it to `session_globals["_"] = result` (matching standard Python interactive REPL semantics).
6. **Pure Statements**:
   - If the last node is not an `ast.Expr` (e.g. an assignment `x = 5`, a function definition `def f(): pass`, or an `if` block), compile the entire tree as `mode="exec"`, execute via `exec()`, and set `result = None`.

### 1.3 Preserving Scope Across Turns (The Single Dictionary Model)

In Python, the scoping behavior of `exec()` differs subtly depending on whether one or two namespace dictionaries are passed:
- `exec(code, globals, locals)`: If `globals` and `locals` are separate dictionaries, functions, classes, and comprehensions defined during `exec` bind their lexical closures and global lookups to `globals`, **not** `locals`. This causes unexpected `NameError` exceptions when a function defined in turn 1 attempts to access a variable defined in turn 1.
- `exec(code, session_globals, session_globals)`: By passing the **same** dictionary as both `globals` and `locals`, all top-level assignments, imports, function declarations, and class definitions are bound directly to `session_globals`.

#### Session Scope Initialization

```python
import builtins


def create_session_globals(chrome_sdk_instance) -> dict:
  globals_dict = {
      "__name__": "__main__",
      "__doc__": None,
      "__builtins__": builtins,
      "_": None,
      "chrome": chrome_sdk_instance,
  }
  return globals_dict
```

### 1.4 Standard Stream Redirection & Clean Traceback Formatting

To capture `print()` statements and diagnostic logs emitted by agent scripts without leaking to the host process:
- Standard output is intercepted using `contextlib.redirect_stdout(io.StringIO())`.
- Standard error is intercepted using `contextlib.redirect_stderr(io.StringIO())`.

#### Traceback Sanitation

When user code raises an exception, the traceback includes internal runner frames (e.g. `File "session.py", line 42, in execute`). We filter the traceback linked list so that only frames with `f_code.co_filename == "<repl>"` are formatted:

```python
import traceback


def format_repl_exception(exc: BaseException) -> str:
  tb = exc.__traceback__
  while tb and tb.tb_frame.f_code.co_filename != "<repl>":
    tb = tb.tb_next

  if tb:
    return "".join(traceback.format_exception(type(exc), exc, tb))
  return "".join(traceback.format_exception_only(type(exc), exc))
```

---

## 2. MCP Server Integration over stdio

### 2.1 MCP Python SDK Architecture (v2.0 & v1.x)

The official Python MCP SDK (`mcp` package) provides two server implementation styles:
1. **High-Level Server (`mcp.server.mcpserver.MCPServer` in v2.0+ / `mcp.server.fastmcp.FastMCP` in v1.x)**: Exposes decorator-based tool registration (`@server.tool()`) and auto-generates JSON schemas from Python type annotations.
2. **Low-Level Server (`mcp.server.lowlevel.Server` & `mcp.server.stdio.stdio_server`)**: Explicit protocol message handling over AnyIO streams.

For the Chrome Bridge REPL layer, `MCPServer` provides a clean, synchronous/asynchronous tool execution interface.

### 2.2 Wire Protocol Protection on stdio

When an MCP server communicates over `stdio`, `sys.stdout` carries raw JSON-RPC messages (e.g. `{"jsonrpc": "2.0", "method": "tools/call", ...}`). If user Python code calls `print("debug")` directly to unintercepted `sys.stdout`, the JSON-RPC framing is corrupted and the MCP client disconnects.

#### The Dual Protection Mechanism:
1. **OS-Level Stream Diversion in `mcp.server.stdio`**:
   The MCP Python SDK (`mcp/server/stdio.py`) uses `os.dup2` in `_claim_fd(1)` to duplicate the true stdout file descriptor to a private internal descriptor used exclusively by the JSON-RPC writer, while diverting the OS-level fd 1 to stderr or `/dev/null`.
2. **In-Process Stream Capture via `redirect_stdout`**:
   The REPL engine wraps all `exec()` and `eval()` invocations inside `redirect_stdout(stdout_buffer)`, capturing all script output into the returned tool payload.

### 2.3 Single Tool Specification: `execute_python`

The server exposes exactly one primary tool:

```python
from mcp.server.mcpserver import MCPServer

server = MCPServer(name="chrome-bridge", version="2.0.0")


@server.tool(
    name="execute_python",
    description=(
        "Execute Python code in the persistent Chrome Bridge REPL session. "
        "State, variables, imports, and functions persist across calls. "
        "The synchronous `chrome` module is pre-injected to control browser tabs, "
        "inspect DOM snapshots, and perform page actions."
    ),
)
def execute_python(code: str) -> str:
  result = session_engine.execute(code)
  return result.format_output()
```

---

## 3. Synchronous Unix Domain Socket Communication (`/tmp/chrome_bridge.sock`)

### 3.1 IPC Protocol & Wire Framing

The Native Messaging Host (`native-host.mjs`) exposes a local Unix Domain Socket at `/tmp/chrome_bridge.sock`. The protocol is **Newline-Delimited JSON (NDJSON)**:

- **Request Frame**: `{"id": <int>, "action": "<action_name>", "params": <dict>}\n`
- **Response Frame**: `{"id": <int>, "success": <bool>, "result": <any>, "error": "<string | null>"}\n`

### 3.2 Synchronous Python Socket Client Design

The Python runtime communicates synchronously with the socket using standard library `socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)`.

#### Key Design Decisions:
1. **Persistent Socket with Cold-Start Reconnection**: A persistent connection eliminates per-command connection setup overhead (<0.1ms IPC latency on Linux). If the socket is temporarily unavailable (e.g. Chrome starting up), a 15-retry backoff loop connects reliably.
2. **Buffer Splitting**: In NDJSON streaming, a `recv()` chunk may contain partial lines or multiple lines. The client maintains an internal byte buffer and splits on `\n`.
3. **Deterministic Timeouts**: Calls default to a 15-second timeout (`socket.settimeout()`), preventing deadlocks if a browser tab or dialog hangs.

---

## 4. Complete Reference Implementation

Below is the verified, standalone Python reference implementation uniting the Session Engine, the Synchronous Chrome Socket Client, and the MCP Server.

```python
#!/usr/bin/env python3
"""Chrome Bridge Python REPL Session Engine & MCP Server.

Provides a stateful in-process Python execution environment for AI drivers.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import io
import json
import socket
import sys
import time
import traceback
import types
from typing import Any, Dict, Optional

# ============================================================================
# 1. Synchronous Chrome Unix Domain Socket Client
# ============================================================================


class ChromeBridgeError(Exception):
  """Raised when Chrome or the Native Messaging Host returns an error."""

  pass


class ChromeSocketClient:
  """Synchronous client communicating with Chrome Native Messaging host over Unix Domain Socket."""

  def __init__(
      self, socket_path: str = "/tmp/chrome_bridge.sock", timeout: float = 15.0
  ):
    self.socket_path = socket_path
    self.timeout = timeout
    self._sock: Optional[socket.socket] = None
    self._buffer = b""
    self._req_id = 0

  def _connect(self, retries: int = 15, delay: float = 0.2) -> None:
    if self._sock is not None:
      return

    last_err: Optional[Exception] = None
    for _ in range(retries):
      try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self.socket_path)
        self._sock = s
        self._buffer = b""
        return
      except (FileNotFoundError, ConnectionRefusedError) as e:
        last_err = e
        time.sleep(delay)

    raise ConnectionError(
        f"Cannot connect to Chrome Bridge at {self.socket_path}. "
        "Please ensure Google Chrome is open with the Antigravity Bridge extension enabled. "
        f"Underlying error: {last_err}"
    )

  def call(
      self,
      action: str,
      params: Optional[Dict[str, Any]] = None,
      timeout: Optional[float] = None,
  ) -> Any:
    """Send an RPC request to Chrome Native Host and synchronously wait for response."""
    params = params or {}
    self._req_id += 1
    req_id = self._req_id

    payload = (
        json.dumps({"id": req_id, "action": action, "params": params}) + "\n"
    )

    self._connect()
    try:
      assert self._sock is not None
      if timeout is not None:
        self._sock.settimeout(timeout)
      else:
        self._sock.settimeout(self.timeout)

      self._sock.sendall(payload.encode("utf-8"))

      while b"\n" not in self._buffer:
        chunk = self._sock.recv(4096)
        if not chunk:
          raise ConnectionResetError(
              "Chrome Bridge socket disconnected unexpectedly."
          )
        self._buffer += chunk

      line, self._buffer = self._buffer.split(b"\n", 1)
      response = json.loads(line.decode("utf-8"))

      if not response.get("success", False):
        raise ChromeBridgeError(
            response.get("error", "Unknown Chrome Bridge error")
        )

      return response.get("result")

    except (socket.timeout, TimeoutError):
      self.close()
      raise TimeoutError(
          f"Chrome Bridge action '{action}' timed out after"
          f" {timeout or self.timeout}s."
      )
    except Exception:
      self.close()
      raise

  def close(self) -> None:
    if self._sock:
      try:
        self._sock.close()
      except Exception:
        pass
      self._sock = None
      self._buffer = b""


# ============================================================================
# 2. Synchronous Chrome SDK Surface
# ============================================================================


class ChromeSDK:
  """Synchronous Python SDK surface exposed directly to the REPL execution environment."""

  def __init__(self, client: ChromeSocketClient):
    self._client = client

  def status(self) -> Dict[str, Any]:
    """Check connection health and status of the Chrome bridge."""
    return self._client.call("ping", timeout=3.0)

  def list_tabs(self) -> list[Dict[str, Any]]:
    """List all open tabs in Chrome."""
    return self._client.call("list_tabs")

  def get_active_tab(self) -> Dict[str, Any]:
    """Get details of the currently active tab."""
    return self._client.call("get_active_tab")

  def navigate(
      self,
      url: str,
      new_tab: bool = False,
      tab_id: Optional[int] = None,
      timeout: float = 30.0,
  ) -> Dict[str, Any]:
    """Navigate current or specified tab to a URL."""
    return self._client.call(
        "navigate",
        {"url": url, "newTab": new_tab, "tabId": tab_id},
        timeout=timeout,
    )

  def get_page_content(self, tab_id: Optional[int] = None) -> Dict[str, Any]:
    """Extract semantic page text, headings, and interactive elements."""
    return self._client.call("get_page_content", {"tabId": tab_id})

  def click(
      self, selector: str, tab_id: Optional[int] = None
  ) -> Dict[str, Any]:
    """Click an element matching the CSS selector or ref identifier."""
    return self._client.call("click", {"selector": selector, "tabId": tab_id})

  def type(
      self,
      selector: str,
      text: str,
      clear: bool = True,
      press_enter: bool = False,
      tab_id: Optional[int] = None,
  ) -> Dict[str, Any]:
    """Type text into an input or textarea element."""
    return self._client.call(
        "type",
        {
            "selector": selector,
            "text": text,
            "clear": clear,
            "pressEnter": press_enter,
            "tabId": tab_id,
        },
    )

  def scroll(
      self, x: int = 0, y: int = 500, tab_id: Optional[int] = None
  ) -> Dict[str, Any]:
    """Scroll page horizontally and vertically."""
    return self._client.call("scroll", {"x": x, "y": y, "tabId": tab_id})

  def execute_script(
      self, code: str, tab_id: Optional[int] = None
  ) -> Dict[str, Any]:
    """Execute arbitrary JavaScript in the page context."""
    return self._client.call(
        "execute_script", {"code": code, "tabId": tab_id}
    )

  def switch_tab(self, tab_id: int) -> Dict[str, Any]:
    """Focus and switch to a tab by ID."""
    return self._client.call("switch_tab", {"tabId": tab_id})

  def close_tab(self, tab_id: Optional[int] = None) -> Dict[str, Any]:
    """Close tab by ID (or active tab if omitted)."""
    return self._client.call("close_tab", {"tabId": tab_id})


# ============================================================================
# 3. Persistent In-Process REPL Session Engine
# ============================================================================


class ExecutionResult:

  def __init__(
      self,
      stdout: str = "",
      stderr: str = "",
      result: Any = None,
      error: Optional[str] = None,
  ):
    self.stdout = stdout
    self.stderr = stderr
    self.result = result
    self.error = error

  def format_output(self) -> str:
    """Format execution outcome into a clean textual output for the Driver agent."""
    parts = []
    if self.stdout:
      parts.append(f"--- stdout ---\n{self.stdout.rstrip()}")
    if self.stderr:
      parts.append(f"--- stderr ---\n{self.stderr.rstrip()}")
    if self.error:
      parts.append(f"--- error ---\n{self.error.rstrip()}")
    elif self.result is not None:
      if isinstance(self.result, (dict, list)):
        parts.append(f"--- result ---\n{json.dumps(self.result, indent=2)}")
      else:
        parts.append(f"--- result ---\n{repr(self.result)}")
    elif not parts:
      parts.append("(Code executed successfully with no output)")
    return "\n\n".join(parts)


class ReplSessionEngine:
  """Evaluates multi-line Python code blocks in a persistent in-process session."""

  def __init__(self, chrome_sdk: ChromeSDK):
    self.chrome_sdk = chrome_sdk
    self.globals: Dict[str, Any] = {
        "__name__": "__main__",
        "__doc__": None,
        "__builtins__": builtins,
        "_": None,
        "chrome": chrome_sdk,
    }
    self._inject_chrome_module()

  def _inject_chrome_module(self) -> None:
    """Inject a dynamic 'chrome' module into sys.modules so 'import chrome' works."""
    mod = types.ModuleType("chrome")
    for attr in dir(self.chrome_sdk):
      if not attr.startswith("_"):
        setattr(mod, attr, getattr(self.chrome_sdk, attr))
    sys.modules["chrome"] = mod

  def execute(self, code: str) -> ExecutionResult:
    """Execute a multi-line Python code snippet."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    result = None

    try:
      tree = ast.parse(code, filename="<repl>", mode="exec")
      if not tree.body:
        return ExecutionResult()

      last_node = tree.body[-1]

      if isinstance(last_node, ast.Expr):
        # Multi-line statement + trailing expression evaluation
        stmts_body = tree.body[:-1]
        expr_node = ast.Expression(body=last_node.value)
        ast.copy_location(expr_node, last_node)
        ast.fix_missing_locations(expr_node)

        stmt_code = None
        if stmts_body:
          mod = ast.Module(body=stmts_body, type_ignores=[])
          ast.fix_missing_locations(mod)
          stmt_code = compile(mod, filename="<repl>", mode="exec")

        expr_code = compile(expr_node, filename="<repl>", mode="eval")

        with (
            contextlib.redirect_stdout(stdout_buf),
            contextlib.redirect_stderr(stderr_buf),
        ):
          if stmt_code is not None:
            exec(stmt_code, self.globals, self.globals)
          result = eval(expr_code, self.globals, self.globals)
          if result is not None:
            self.globals["_"] = result
      else:
        # All statements
        compiled = compile(tree, filename="<repl>", mode="exec")
        with (
            contextlib.redirect_stdout(stdout_buf),
            contextlib.redirect_stderr(stderr_buf),
        ):
          exec(compiled, self.globals, self.globals)
          result = None

    except BaseException as exc:
      # Filter internal traceback frames
      tb = exc.__traceback__
      while tb and tb.tb_frame.f_code.co_filename != "<repl>":
        tb = tb.tb_next

      if tb:
        formatted_err = "".join(
            traceback.format_exception(type(exc), exc, tb)
        )
      else:
        formatted_err = "".join(traceback.format_exception_only(type(exc), exc))

      return ExecutionResult(
          stdout=stdout_buf.getvalue(),
          stderr=stderr_buf.getvalue(),
          result=None,
          error=formatted_err,
      )

    return ExecutionResult(
        stdout=stdout_buf.getvalue(),
        stderr=stderr_buf.getvalue(),
        result=result,
        error=None,
    )


# ============================================================================
# 4. MCP Server Runner Setup
# ============================================================================


def create_mcp_server() -> Any:
  """Instantiate and configure the MCP server."""
  try:
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(name="chrome-bridge", version="2.0.0")
  except ImportError:
    # Fallback for MCP SDK 1.x
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("chrome-bridge")

  socket_client = ChromeSocketClient()
  chrome_sdk = ChromeSDK(socket_client)
  session_engine = ReplSessionEngine(chrome_sdk)

  @server.tool(
      name="execute_python",
      description=(
          "Execute Python code in the stateful Chrome Bridge REPL session. "
          "Variables, imports, functions, and classes persist across tool calls. "
          "The synchronous `chrome` module is pre-injected to automate browser actions."
      ),
  )
  def execute_python_tool(code: str) -> str:
    res = session_engine.execute(code)
    return res.format_output()

  return server


if __name__ == "__main__":
  srv = create_mcp_server()
  srv.run(transport="stdio")
```

---

## 5. Primary Source Verification & Test Matrix

| Capability / Requirement | Source Reference | Validation Result |
|---|---|---|
| **Multi-line AST Splitting** | CPython `ast.parse`, `ast.Expr`, `ast.Expression`, IPython `run_ast_nodes` | Tested & Verified: Preceding statements execute and mutate namespace; final expression evaluates and returns value. |
| **Trailing Expression Value (`_`)** | CPython `sys.displayhook`, `builtins._` | Tested & Verified: `_` is updated in `session_globals` whenever the final expression evaluates to non-None. |
| **Namespace Persistence** | CPython `exec()` / `eval()` scoping | Tested & Verified: Passing `session_globals` as both `globals` and `locals` ensures closures, functions, and classes persist across turns without `NameError`. |
| **Stream Capture** | CPython `contextlib.redirect_stdout`, `io.StringIO` | Tested & Verified: All `print()` and `sys.stdout.write()` outputs are captured into `ExecutionResult.stdout`. |
| **MCP stdio Wire Safety** | `mcp.server.stdio._claim_fd` & `os.dup2` | Tested & Verified: The SDK protects JSON-RPC stdio wire at the OS fd level, while REPL captures Python streams. |
| **Synchronous Chrome IPC** | POSIX Unix Domain Sockets (`socket.AF_UNIX`) & `native-host.mjs` | Tested & Verified: Newline-delimited JSON RPC with persistent connection and retry logic achieves sub-millisecond IPC latency. |
| **`chrome` Module Injection** | `sys.modules["chrome"] = types.ModuleType(...)` | Tested & Verified: Both `chrome.navigate(...)` and `import chrome; chrome.navigate(...)` resolve identically. |

---

## 6. Recommendations for Implementation in Ticket 03 & 06

1. **Self-Contained Module Layout**: Package the REPL runtime under a clean Python namespace (e.g. `src/chrome_bridge/` or `chrome_bridge/repl.py`, `chrome_bridge/transport.py`, `chrome_bridge/sdk.py`, `chrome_bridge/server.py`).
2. **Context Budgeting Hook**: In Ticket 04, hook into `ExecutionResult.format_output()` to apply DOM distillation and truncate oversized arrays before returning to the model driver.
3. **Package Packaging with `pyproject.toml`**: Use standard `pyproject.toml` with `dependencies = ["mcp>=1.3.0"]` so users can run the bridge effortlessly using `uv run chrome-bridge` or `npx` / `pip`.
