"""Tests for self-healing Doctor engine and automatic repair."""

import json
import os
import stat
import tempfile
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from setup_host import (
    run_doctor,
    check_stale_ipc,
    check_file_permissions,
    check_mcp_configs_health,
    repair_mcp_config,
    TerminalUI,
)


def test_check_stale_ipc_unlinks_dead_socket(tmp_path):
    """Test stale socket detection and unlinking when host is dead."""
    sock_path = tmp_path / "antigravity_chrome_bridge.sock"
    sock_path.write_text("dummy socket")

    with patch("tempfile.gettempdir", return_value=str(tmp_path)), \
         patch("setup_host.IS_WINDOWS", False), \
         patch("socket.socket") as mock_sock_cls:
        # Mock connection failure (dead socket)
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = ConnectionRefusedError("Connection refused")
        mock_sock_cls.return_value.__enter__.return_value = mock_sock

        issues = check_stale_ipc(auto_fix=True)
        assert len(issues) == 1
        assert "Stale" in issues[0]["title"]
        assert issues[0]["fixed"] is True
        assert not sock_path.exists()


def test_check_file_permissions_repairs_mode(tmp_path):
    """Test permission verification and 0755 repair on POSIX launchers."""
    launcher = tmp_path / "native-host.sh"
    launcher.write_text("#!/bin/sh\necho test\n")
    launcher.chmod(0o644)  # No execute bit

    with patch("setup_host.IS_WINDOWS", False):
        issues = check_file_permissions(tmp_path, auto_fix=True)
        assert len(issues) >= 1
        assert launcher.stat().st_mode & stat.S_IXUSR


def test_repair_mcp_config_creates_backup_and_fixes(tmp_path):
    """Test corrupted JSON recovery creates a backup and rewrites valid JSON."""
    bad_json = tmp_path / "corrupted.json"
    bad_json.write_text("{ this is malformed json !!!")

    repaired, backup_path = repair_mcp_config(
        bad_json,
        "TestClient",
        command="uvx",
        args=["antigravity-chrome-bridge", "mcp"],
    )

    assert repaired is True
    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.read_text() == "{ this is malformed json !!!"

    # Verify repaired content is valid JSON with chrome-bridge
    data = json.loads(bad_json.read_text(encoding="utf-8"))
    assert data["mcpServers"]["chrome-bridge"]["command"] == "uvx"


def test_run_doctor_clean_pass(tmp_path):
    """Test doctor passes cleanly on a fully configured directory."""
    install_dir = tmp_path / ".chrome-bridge"
    install_dir.mkdir()
    host_py = install_dir / "native_host.py"
    host_py.write_text("# host")
    host_py.chmod(0o755)
    (install_dir / "mcp_server.py").write_text("# mcp")
    launcher = install_dir / "native-host.sh"
    launcher.write_text("#!/bin/sh")
    launcher.chmod(0o755)

    home_dir = tmp_path / "home"
    manifest_dir = home_dir / ".config" / "google-chrome" / "NativeMessagingHosts"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "com.chrome_bridge.native.json").write_text('{"name": "com.chrome_bridge.native"}')

    with patch("setup_host.resolve_home_dir", return_value=home_dir), \
         patch("setup_host.resolve_install_dir", return_value=install_dir), \
         patch("tempfile.gettempdir", return_value=str(tmp_path)):
        exit_code = run_doctor(install_dir=install_dir, home_dir=home_dir, auto_fix=False, quiet=True)
        assert exit_code == 0
