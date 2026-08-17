"""Comprehensive end-to-end integration tests for Chrome Bridge Python REPL and MCP Server."""

import json
import os
import socket
import threading
import time
import pytest
from repl_engine import PythonReplSession
from chrome_sdk import ChromeSocketClient, Chrome, Tab, normalize_locator
from mcp_server import execute_python, _SESSION


class MockSocketBridge:
    """Mock Unix Domain Socket / TCP loopback server simulating Chrome Extension native host bridge."""

    def __init__(self, socket_path="/tmp/test_chrome_bridge.sock", port_file=None):
        self.socket_path = socket_path
        self.port_file = port_file or (os.path.splitext(socket_path)[0] + ".port")
        self._server = None
        self._thread = None
        self._running = False
        self.recorded_requests = []
        self.responses = {}
        self.use_tcp = os.name == "nt" or not hasattr(socket, "AF_UNIX")

    def start(self):
        if self.use_tcp:
            if os.path.exists(self.port_file):
                try:
                    os.unlink(self.port_file)
                except Exception:
                    pass
            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server.bind(("127.0.0.1", 0))
            port = self._server.getsockname()[1]
            with open(self.port_file, "w", encoding="utf-8") as f:
                f.write(str(port))
            self._server.listen(5)
        else:
            if os.path.exists(self.socket_path):
                try:
                    os.unlink(self.socket_path)
                except Exception:
                    pass

            self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server.bind(self.socket_path)
            self._server.listen(5)

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while self._running:
            try:
                conn, _ = self._server.accept()
            except Exception:
                break
            client_thread = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
            client_thread.start()

    def _handle_client(self, conn):
        buf = b""
        while self._running:
            try:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    req = json.loads(line.decode("utf-8"))
                    self.recorded_requests.append(req)
                    action = req.get("action")
                    req_id = req.get("id")

                    # Handle action response
                    handler = self.responses.get(action)
                    if callable(handler):
                        res_obj = handler(req.get("params", {}))
                    else:
                        res_obj = handler or {"status": "ok"}

                    if isinstance(res_obj, dict) and res_obj.get("__error"):
                        resp = {"id": req_id, "success": False, "error": res_obj["__error"]}
                    else:
                        resp = {"id": req_id, "success": True, "result": res_obj}

                    conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")
            except Exception:
                break
        conn.close()

    def stop(self):
        self._running = False
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
        if self.use_tcp:
            if os.path.exists(self.port_file):
                try:
                    os.unlink(self.port_file)
                except Exception:
                    pass
        else:
            if os.path.exists(self.socket_path):
                try:
                    os.unlink(self.socket_path)
                except Exception:
                    pass


@pytest.fixture
def mock_bridge():
    import tempfile
    sock_path = os.path.join(tempfile.gettempdir(), "test_chrome_bridge.sock")
    bridge = MockSocketBridge(sock_path)

    # Configure default responses
    bridge.responses = {
        "ping": {"pong": True, "timestamp": 1234567890},
        "list_tabs": [
            {"id": 1, "title": "GitHub Dashboard", "url": "https://github.com", "active": True},
            {"id": 2, "title": "Hacker News", "url": "https://news.ycombinator.com", "active": False},
        ],
        "get_tab": lambda p: {"id": p.get("tabId", 1), "title": "Mock Tab", "url": "https://example.com", "active": True},
        "get_page_content": {
            "snapshot": 'PAGE: "GitHub Dashboard" (https://github.com)\n- heading[level=1]: "Pull Requests"\n- input:text [#1] "Search" (placeholder="Search all pull requests")\n- button [#2] "Filter"\n- link [#3] "New Pull Request" (href="/new")',
            "totalInteractive": 3,
            "epoch": 1001,
        },
        "click": lambda p: {"status": "ok", "action": "click", "target": str(p.get("target"))},
        "type": lambda p: {"status": "ok", "action": "type", "target": str(p.get("target")), "currentValue": p.get("text")},
        "scroll": lambda p: {"scrolled": {"x": p.get("x", 0), "y": p.get("y", 500)}},
        "navigate": lambda p: {"tabId": p.get("tabId", 1), "url": p.get("url")},
        "execute_script": lambda p: 42 if "21 * 2" in p.get("code", "") else "eval_result",
    }

    bridge.start()
    yield bridge
    bridge.stop()


def test_full_capability_multi_turn_script(mock_bridge):
    client = ChromeSocketClient(socket_path=mock_bridge.socket_path)
    chrome = Chrome(client=client)
    session = PythonReplSession(globals_dict={"chrome": chrome})

    # Turn 1: Inspect page snapshot and tabs
    turn1_code = """
tabs = chrome.tabs
snapshot = chrome.snapshot()
f"Found {len(tabs)} tabs. Snapshot has {len(snapshot.splitlines())} lines."
"""
    out1 = session.execute(turn1_code)
    assert "[result]" in out1
    assert "Found 2 tabs. Snapshot has 5 lines." in out1

    # Turn 2: State persistence & multi-step automation workflow in one script
    turn2_code = """
results = []
for ref in [1, 2, 3]:
    res = chrome.click(ref)
    results.append(res['action'])

chrome.type("[#1]", "query test", clear=True, press_enter=True)
results.append("typed")
results
"""
    out2 = session.execute(turn2_code)
    assert "[result]" in out2
    assert "['click', 'click', 'click', 'typed']" in out2


def test_mcp_execute_python_wrapper():
    out = execute_python("x = 55\nx * 2")
    assert "[result]" in out
    assert "110" in out

    out2 = execute_python("x + 10")
    assert "[result]" in out2
    assert "65" in out2


def test_diagnostics_on_stale_ref_id(mock_bridge):
    # Setup mock to return structured element not found error
    mock_bridge.responses["click"] = lambda p: {
        "__error": {
            "code": "ELEMENT_NOT_FOUND",
            "target": str(p.get("target")),
            "stale": True,
            "suggestions": [{"ref": "#18", "role": "button", "name": "Checkout"}],
            "url": "https://store.example.com/checkout",
        }
    }

    client = ChromeSocketClient(socket_path=mock_bridge.socket_path)
    chrome = Chrome(client=client)
    session = PythonReplSession(globals_dict={"chrome": chrome})

    out = session.execute("chrome.click(14)")
    assert "[error]" in out
    assert "ElementNotFoundError" in out
    assert "DOM mutated" in out
    assert "Did you mean: [#18] (button 'Checkout')?" in out
    assert "[diagnostic_auto_snapshot]" in out


def test_diagnostics_on_action_interception(mock_bridge):
    mock_bridge.responses["click"] = lambda p: {
        "__error": {
            "code": "ACTION_INTERCEPTED",
            "target": str(p.get("target")),
            "interceptorTag": "div.modal-backdrop",
            "interceptorRef": "99",
            "interceptorDesc": "Cookie Consent Modal",
        }
    }

    client = ChromeSocketClient(socket_path=mock_bridge.socket_path)
    chrome = Chrome(client=client)
    session = PythonReplSession(globals_dict={"chrome": chrome})

    out = session.execute("chrome.click('[#5]')")
    assert "[error]" in out
    assert "ActionInterceptionError" in out
    assert "intercepted by overlapping element [#99] (Cookie Consent Modal)" in out


def test_mcp_server_stdio_jsonrpc():
    import subprocess
    import sys

    # Run mcp_server.py as a subprocess over stdio
    proc = subprocess.Popen(
        [sys.executable, "mcp_server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # 1. Send MCP initialize request
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        }
        proc.stdin.write(json.dumps(init_req) + "\n")
        proc.stdin.flush()

        init_line = proc.stdout.readline()
        assert init_line, "Expected initialize response from MCP server"
        init_resp = json.loads(init_line)
        assert init_resp.get("id") == 1
        assert "serverInfo" in init_resp.get("result", {})

        # 2. Send initialized notification
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        # 3. Call execute_python tool
        tool_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "execute_python",
                "arguments": {
                    "code": "a = 21\na * 2"
                },
            },
        }
        proc.stdin.write(json.dumps(tool_req) + "\n")
        proc.stdin.flush()

        tool_line = proc.stdout.readline()
        assert tool_line, "Expected tool response from MCP server"
        tool_resp = json.loads(tool_line)
        assert tool_resp.get("id") == 2
        content_items = tool_resp.get("result", {}).get("content", [])
        assert len(content_items) > 0
        text_out = content_items[0].get("text", "")
        assert "[result]" in text_out
        assert "42" in text_out

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()


def test_wait_for_and_wait_for_url_synchronization(mock_bridge):
    # Mock wait_for and wait_for_url responses
    mock_bridge.responses["wait_for"] = lambda p: True
    mock_bridge.responses["wait_for_url"] = lambda p: True

    client = ChromeSocketClient(socket_path=mock_bridge.socket_path)
    chrome = Chrome(client=client)
    session = PythonReplSession(globals_dict={"chrome": chrome})

    code = """
res1 = chrome.wait_for('[#2]', timeout=2.0)
res2 = chrome.wait_for_url(r'https://.*', timeout=2.0)
(res1, res2)
"""
    out = session.execute(code)
    assert "[result]" in out
    assert "(True, True)" in out


def test_wait_for_timeout_diagnostics(mock_bridge):
    # Mock wait_for timeout error with auto_snapshot
    mock_bridge.responses["wait_for"] = lambda p: {
        "__error": {
            "code": "TIMEOUT",
            "target": str(p.get("target")),
            "timeout": 2.0,
            "readyState": "complete",
            "domState": "hidden in DOM (display: none)",
            "url": "https://example.com/checkout",
            "auto_snapshot": "PAGE: \"Checkout\" (https://example.com/checkout)\n- button [#1] \"Pay Now\""
        }
    }

    client = ChromeSocketClient(socket_path=mock_bridge.socket_path)
    chrome = Chrome(client=client)
    session = PythonReplSession(globals_dict={"chrome": chrome})

    out = session.execute("chrome.wait_for('[#99]', timeout=2.0)")
    assert "[error]" in out
    assert "NavigationTimeoutError" in out
    assert "hidden in DOM (display: none)" in out
    assert "[diagnostic_auto_snapshot]" in out
    assert "PAGE: \"Checkout\"" in out

