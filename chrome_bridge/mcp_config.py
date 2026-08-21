"""AI agent MCP client configuration discovery, upserting, and validation."""

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .manifests import IS_MAC
from .ui import bold, dim, green, yellow


class MCPClientInfo:
    """Descriptor for a detected AI agent MCP client."""

    def __init__(
        self,
        name: str,
        config_path: Path,
        is_present: bool,
        is_configured: bool = False,
    ):
        self.name = name
        self.config_path = config_path
        self.is_present = is_present
        self.is_configured = is_configured


def detect_mcp_clients(home_dir: Path) -> List[MCPClientInfo]:
    """Inspect AI agent MCP client configurations."""
    app_data = os.environ.get("APPDATA")
    client_defs = [
        ("Claude Code", home_dir / ".claude.json"),
        ("Antigravity Global", home_dir / ".agent" / "mcp_config.json"),
        ("Antigravity Config", home_dir / ".config" / "antigravity" / "mcp_config.json"),
        ("Antigravity CLI", home_dir / ".gemini" / "antigravity-cli" / "mcp_config.json"),
        ("Claude Desktop", home_dir / ".config" / "Claude" / "claude_desktop_config.json"),
        ("Cursor", home_dir / ".cursor" / "mcp.json"),
        ("Windsurf", home_dir / ".codeium" / "windsurf" / "mcp_config.json"),
        ("Zed", home_dir / ".config" / "zed" / "settings.json"),
        ("Codex CLI", home_dir / ".codex" / "config.json"),
        ("Codex MCP", home_dir / ".codex" / "mcp.json"),
        ("Pi Code", home_dir / ".pi" / "mcp.json"),
        ("Pi Agent", home_dir / ".pi" / "agent" / "mcp.json"),
    ]
    if IS_MAC:
        client_defs.append(("Claude Desktop (macOS)", home_dir / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"))
    if app_data:
        client_defs.append(("Claude Desktop (Windows)", Path(app_data) / "Claude" / "claude_desktop_config.json"))

    results: List[MCPClientInfo] = []
    for name, path in client_defs:
        if name in ("Codex MCP", "Pi Agent"):
            is_present = path.exists()
        else:
            is_present = path.exists() or path.parent.exists()
        is_conf = False
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    if "mcpServers" in data and isinstance(data["mcpServers"], dict):
                        is_conf = "chrome-bridge" in data["mcpServers"]
                    elif "context_servers" in data and isinstance(data["context_servers"], dict):
                        is_conf = "chrome-bridge" in data["context_servers"]
            except Exception:
                pass
        results.append(MCPClientInfo(
            name=name,
            config_path=path,
            is_present=is_present,
            is_configured=is_conf,
        ))
    return results


def update_mcp_client_config(
    file_path: Path,
    client_name: str,
    command: str,
    args: List[str],
    quiet: bool = False,
    schema_key: Optional[str] = None,
) -> bool:
    """Non-destructively upsert chrome-bridge entry in an MCP client configuration file."""
    try:
        key = schema_key or "mcpServers"
        config: Dict[str, Any] = {key: {}}
        if file_path.exists():
            try:
                raw = file_path.read_text(encoding="utf-8")
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    config = loaded
                if not schema_key:
                    if "mcp_servers" in config and isinstance(config["mcp_servers"], dict):
                        key = "mcp_servers"
                    elif "mcpServers" in config and isinstance(config["mcpServers"], dict):
                        key = "mcpServers"
                if key not in config or not isinstance(config[key], dict):
                    config[key] = {}
            except Exception:
                if not quiet:
                    print(f"  {yellow(f'⚠️ Could not parse JSON in {file_path}, skipping...')}")
                return False
        else:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        config[key]["chrome-bridge"] = {
            "command": command,
            "args": args,
        }

        file_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        if not quiet:
            print(f"  {green('✓')} Configured {bold(client_name)}: {dim(str(file_path))}")
        return True
    except Exception as err:
        if not quiet:
            print(f"  {yellow(f'⚠️ Could not update {file_path}:')} {err}")
        return False


def configure_all_mcp_clients(
    install_dir: Path,
    home_dir: Path,
    python_exec: str,
    is_dev: bool = False,
    quiet: bool = False,
) -> None:
    """Update MCP configurations across Claude Code, Antigravity, Claude Desktop, Cursor, Codex, and Pi Code."""
    if is_dev:
        mcp_script = (install_dir / "mcp_server.py").resolve()
        command = python_exec
        args = [str(mcp_script)]
    else:
        command = "uvx"
        args = ["antigravity-chrome-bridge", "mcp"]

    # Claude Code (~/.claude.json)
    update_mcp_client_config(home_dir / ".claude.json", "Claude Code", command, args, quiet)

    # Antigravity Global, Config & CLI
    update_mcp_client_config(home_dir / ".agent" / "mcp_config.json", "Antigravity Global MCP", command, args, quiet)
    update_mcp_client_config(home_dir / ".config" / "antigravity" / "mcp_config.json", "Antigravity Config MCP", command, args, quiet)
    update_mcp_client_config(home_dir / ".gemini" / "antigravity-cli" / "mcp_config.json", "Antigravity CLI MCP", command, args, quiet)

    # Claude Desktop
    app_data = os.environ.get("APPDATA")
    claude_desktop_paths = [
        home_dir / ".config" / "Claude" / "claude_desktop_config.json",
        home_dir / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
    ]
    if app_data:
        claude_desktop_paths.append(Path(app_data) / "Claude" / "claude_desktop_config.json")

    for p in claude_desktop_paths:
        if p.parent.exists():
            update_mcp_client_config(p, "Claude Desktop", command, args, quiet)

    # Cursor
    cursor_dir = home_dir / ".cursor"
    if cursor_dir.exists():
        update_mcp_client_config(cursor_dir / "mcp.json", "Cursor", command, args, quiet)

    # Codex CLI (~/.codex/config.json & ~/.codex/mcp.json)
    codex_dir = home_dir / ".codex"
    update_mcp_client_config(codex_dir / "config.json", "Codex CLI", command, args, quiet, schema_key="mcp_servers")
    if (codex_dir / "mcp.json").exists():
        update_mcp_client_config(codex_dir / "mcp.json", "Codex MCP", command, args, quiet)

    # Pi Code (~/.pi/mcp.json & ~/.pi/agent/mcp.json)
    pi_dir = home_dir / ".pi"
    update_mcp_client_config(pi_dir / "mcp.json", "Pi Code", command, args, quiet)
    if (pi_dir / "agent").exists():
        update_mcp_client_config(pi_dir / "agent" / "mcp.json", "Pi Agent", command, args, quiet)


def repair_mcp_config(
    file_path: Path,
    client_name: str,
    command: str = "uvx",
    args: Optional[List[str]] = None,
) -> Tuple[bool, Optional[Path]]:
    """Safely create a timestamped backup and repair/upsert chrome-bridge MCP config."""
    if args is None:
        args = ["antigravity-chrome-bridge", "mcp"]

    backup_path = None
    if file_path.exists():
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_path = file_path.with_name(f"{file_path.name}.bak.{timestamp}")
            shutil.copy2(file_path, backup_path)
        except Exception:
            pass

    config: Dict[str, Any] = {"mcpServers": {}}
    if file_path.exists():
        try:
            raw = file_path.read_text(encoding="utf-8")
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                config = loaded
        except Exception:
            pass

    if "mcpServers" not in config or not isinstance(config["mcpServers"], dict):
        config["mcpServers"] = {}

    config["mcpServers"]["chrome-bridge"] = {
        "command": command,
        "args": args,
    }

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return True, backup_path


def check_mcp_configs_health(home_dir: Path, auto_fix: bool = False) -> List[Dict[str, Any]]:
    """Inspect all present MCP configs for syntax corruption and missing entries."""
    clients = detect_mcp_clients(home_dir)
    issues = []

    for client in clients:
        if client.is_present and client.config_path.exists():
            try:
                raw = client.config_path.read_text(encoding="utf-8")
                loaded = json.loads(raw)
                if not isinstance(loaded, dict):
                    raise ValueError("Root JSON is not an object")
                has_cb = False
                if "mcpServers" in loaded and isinstance(loaded["mcpServers"], dict):
                    has_cb = "chrome-bridge" in loaded["mcpServers"]
                elif "context_servers" in loaded and isinstance(loaded["context_servers"], dict):
                    has_cb = "chrome-bridge" in loaded["context_servers"]

                if not has_cb:
                    fixed = False
                    if auto_fix:
                        repaired, _ = repair_mcp_config(client.config_path, client.name)
                        fixed = repaired
                    issues.append({
                        "type": "mcp_missing",
                        "title": f"{client.name}: Missing chrome-bridge MCP registration",
                        "detail": f"File {client.config_path} exists but does not register chrome-bridge.",
                        "fixed": fixed,
                    })
            except Exception as e:
                fixed = False
                if auto_fix:
                    repaired, bk = repair_mcp_config(client.config_path, client.name)
                    fixed = repaired
                issues.append({
                    "type": "mcp_corrupted",
                    "title": f"{client.name}: Corrupted or malformed JSON",
                    "detail": f"File {client.config_path} could not be parsed: {e}",
                    "fixed": fixed,
                })

    return issues


__all__ = [
    "MCPClientInfo",
    "detect_mcp_clients",
    "update_mcp_client_config",
    "configure_all_mcp_clients",
    "repair_mcp_config",
    "check_mcp_configs_health",
]
