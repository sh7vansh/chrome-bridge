"""Tests for live extension handshake listener and stdio host simulation."""

import io
import json
import struct
import sys
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from setup_host import (
    simulate_native_host,
    wait_for_extension_handshake,
    TerminalUI,
)


def test_simulate_native_host_success(tmp_path):
    """Test stdio simulation launches native_host.py and exchanges length-prefixed packet."""
    repo_root = Path(__file__).resolve().parent.parent
    native_host_py = repo_root / "native_host.py"

    if not native_host_py.exists():
        pytest.skip("native_host.py not found in repo root")

    success, message, latency_ms = simulate_native_host(python_exec=sys.executable, host_script=native_host_py)
    assert success is True
    assert "operational" in message.lower() or "verified" in message.lower()
    assert latency_ms >= 0


def test_wait_for_extension_handshake_immediate_connection(tmp_path):
    """Test live handshake listener succeeds immediately when socket is active."""
    sock_file = tmp_path / "antigravity_chrome_bridge.sock"
    sock_file.write_text("mock")

    mock_sock = MagicMock()
    mock_sock.__enter__.return_value = mock_sock
    mock_sock.recv.return_value = json.dumps({"id": 1, "status": "ok", "action": "ping", "tabs": [{"id": 1, "title": "GitHub", "url": "https://github.com"}]}).encode("utf-8") + b"\n"

    with patch("setup_host.IS_WINDOWS", False), \
         patch("tempfile.gettempdir", return_value=str(tmp_path)), \
         patch("socket.socket", return_value=mock_sock):

        res = wait_for_extension_handshake(timeout_sec=1.0, stream=io.StringIO(), force_non_interactive=True)
        assert res is not None
        assert res.get("status") == "ok"


def test_wait_for_extension_handshake_timeout(tmp_path):
    """Test live handshake listener times out cleanly without errors."""
    with patch("setup_host.IS_WINDOWS", False), \
         patch("tempfile.gettempdir", return_value=str(tmp_path)):
        
        res = wait_for_extension_handshake(timeout_sec=0.1, stream=io.StringIO(), force_non_interactive=True)
        assert res is None
