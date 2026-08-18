"""Tests for smart multi-platform browser and AI agent discovery prober."""

import os
import sys
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from setup_host import (
    detect_running_browsers,
    detect_installed_browsers,
    detect_mcp_clients,
    BrowserInfo,
    MCPClientInfo,
)


def test_detect_running_browsers_linux(tmp_path):
    """Test Linux process probing via /proc."""
    proc_dir = tmp_path / "proc"
    proc_dir.mkdir()
    
    # Mock PID 1234 running google-chrome
    p1 = proc_dir / "1234"
    p1.mkdir()
    (p1 / "comm").write_text("chrome\n")
    (p1 / "cmdline").write_bytes(b"/opt/google/chrome/chrome\x00--type=normal\x00")

    # Mock PID 5678 running brave
    p2 = proc_dir / "5678"
    p2.mkdir()
    (p2 / "comm").write_text("brave\n")
    (p2 / "cmdline").write_bytes(b"/usr/bin/brave-browser\x00")

    with patch("setup_host.IS_LINUX", True), \
         patch("setup_host.IS_MAC", False), \
         patch("setup_host.IS_WINDOWS", False), \
         patch("setup_host.PROCDIR_OVERRIDE", proc_dir):
        running = detect_running_browsers()
        assert any("Chrome" in b for b in running)
        assert any("Brave" in b for b in running)


def test_detect_installed_browsers(tmp_path):
    """Test detection of installed browsers based on config paths and executables."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    
    # Create fake chrome config dir
    chrome_config = home_dir / ".config" / "google-chrome"
    chrome_config.mkdir(parents=True)

    with patch("setup_host.IS_LINUX", True), \
         patch("setup_host.IS_MAC", False), \
         patch("setup_host.IS_WINDOWS", False):
        browsers = detect_installed_browsers(home_dir)
        chrome_targets = [b for b in browsers if "Google Chrome" in b.name]
        assert len(chrome_targets) > 0
        assert chrome_targets[0].is_installed is True


def test_detect_mcp_clients(tmp_path):
    """Test detection of active AI agent MCP configurations."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    # Create fake claude.json with chrome-bridge configured
    claude_json = home_dir / ".claude.json"
    claude_json.write_text('{"mcpServers": {"chrome-bridge": {"command": "uvx"}}}')

    # Create empty cursor dir
    cursor_dir = home_dir / ".cursor"
    cursor_dir.mkdir()

    clients = detect_mcp_clients(home_dir)
    claude_client = next(c for c in clients if c.name == "Claude Code")
    assert claude_client.is_present is True
    assert claude_client.is_configured is True

    cursor_client = next(c for c in clients if c.name == "Cursor")
    assert cursor_client.is_present is True
    assert cursor_client.is_configured is False
