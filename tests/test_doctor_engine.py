"""Unit tests for chrome_bridge.doctor subsystem."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from chrome_bridge.doctor import (
    check_stale_ipc,
    check_file_permissions,
    run_doctor,
)


def test_check_stale_ipc_posix_no_socket(tmp_path):
    with patch("chrome_bridge.doctor._is_windows", return_value=False), \
         patch("tempfile.gettempdir", return_value=str(tmp_path)):
        issues = check_stale_ipc(auto_fix=False)
        assert len(issues) == 0


def test_check_stale_ipc_detects_unresponsive_socket(tmp_path):
    dead_sock = tmp_path / "antigravity_chrome_bridge.sock"
    dead_sock.touch()

    with patch("chrome_bridge.doctor._is_windows", return_value=False), \
         patch("tempfile.gettempdir", return_value=str(tmp_path)):
        issues = check_stale_ipc(auto_fix=True)
        assert len(issues) == 1
        assert issues[0]["fixed"] is True
        assert not dead_sock.exists()
