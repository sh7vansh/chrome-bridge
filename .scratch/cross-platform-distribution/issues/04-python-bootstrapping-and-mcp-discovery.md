# 04 — Smart Python Bootstrapping & Multi-Client MCP Auto-Discovery

**What to build:**
The setup workflow probes for Python 3.10+ and `uv`, automatically initializes the project `.venv` virtual environment, installs dependencies, and automatically discovers and configures MCP configuration files for Claude Desktop (macOS, Windows, Linux), Antigravity/Gemini CLI, and Cursor using absolute executable paths.

**Blocked by:** 01 — Cross-Platform IPC Transport Layer & Diagnostic Recovery, 03 — Automated Windows Registry & Native Messaging Host Setup

**Status:** done

- [x] Setup script detects `uv` or `python3` / `py -3.11`, creates `.venv`, and installs dependencies from `requirements.txt`.
- [x] If compatible Python runtime is missing, script halts cleanly with clear, platform-specific installation instructions (Homebrew, Winget, Apt).
- [x] `setup-host.mjs` discovers and auto-configures MCP server entries across:
  - Claude Desktop on macOS (`~/Library/Application Support/Claude/claude_desktop_config.json`)
  - Claude Desktop on Windows (`%APPDATA%/Claude/claude_desktop_config.json`)
  - Claude Desktop on Linux (`~/.config/Claude/claude_desktop_config.json`)
  - Antigravity / Gemini CLI (`~/.agent/mcp_config.json`, `~/.gemini/antigravity-cli/mcp_config.json`)
  - Cursor (`~/.cursor/mcp.json`)
- [x] Configured MCP commands reference the absolute Python interpreter path inside `.venv` (`.venv/bin/python` or `.venv/Scripts/python.exe`).
