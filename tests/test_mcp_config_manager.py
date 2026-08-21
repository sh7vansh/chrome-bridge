"""Unit tests for chrome_bridge.mcp_config subsystem."""
import json
import pytest
from pathlib import Path

from chrome_bridge.mcp_config import (
    MCPClientInfo,
    detect_mcp_clients,
    update_mcp_client_config,
    configure_all_mcp_clients,
    repair_mcp_config,
    check_mcp_configs_health,
)


def test_update_mcp_client_config_creates_new(tmp_path):
    cfg_file = tmp_path / "mcp.json"
    ok = update_mcp_client_config(cfg_file, "TestClient", "uvx", ["chrome-bridge", "mcp"], quiet=True)
    assert ok is True
    assert cfg_file.exists()

    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert "chrome-bridge" in data["mcpServers"]
    assert data["mcpServers"]["chrome-bridge"]["command"] == "uvx"


def test_update_mcp_client_config_preserves_existing_servers(tmp_path):
    cfg_file = tmp_path / "mcp.json"
    initial = {"mcpServers": {"other-server": {"command": "other-cmd", "args": []}}}
    cfg_file.write_text(json.dumps(initial), encoding="utf-8")

    ok = update_mcp_client_config(cfg_file, "TestClient", "python3", ["mcp_server.py"], quiet=True)
    assert ok is True

    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert "other-server" in data["mcpServers"]
    assert "chrome-bridge" in data["mcpServers"]


def test_repair_mcp_config_creates_backup(tmp_path):
    cfg_file = tmp_path / "broken.json"
    cfg_file.write_text("NOT_VALID_JSON", encoding="utf-8")

    ok, backup = repair_mcp_config(cfg_file, "BrokenClient")
    assert ok is True
    assert backup is not None
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "NOT_VALID_JSON"

    repaired = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert "chrome-bridge" in repaired["mcpServers"]
