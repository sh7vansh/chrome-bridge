# Specification: Cross-Platform Support & Zero-Friction Distribution

## Problem Statement

When external developers clone or install Antigravity Chrome Bridge from GitHub, the setup experience is fragile and platform-restricted:
1. It currently only works reliably on Linux because IPC paths (`/tmp/chrome_bridge.sock`) and Native Messaging Host registration directories are POSIX-only.
2. Windows is completely unsupported because Windows Chrome does not read JSON manifests from filesystem paths (it requires Windows Registry keys in `HKCU`) and cannot directly launch Node `.mjs` scripts without an executable batch wrapper (`.bat`).
3. External users face severe friction configuring multiple AI clients (Claude Desktop, Antigravity, Cursor) and setting up Python virtual environments manually.
4. If a user loads the unpacked extension without a pinned public key, Chrome generates a random Extension ID that breaks the Native Messaging allowlist.

## Solution

A zero-friction, cross-platform distribution and runtime architecture supporting Linux, macOS, and Windows:
1. **Platform-Aware Local IPC**: Dynamic resolution of temp-directory sockets (`tempfile.gettempdir()` on POSIX) and Windows-compatible IPC (`%TEMP%` / Named Pipes) ensuring zero port collisions and zero local network exposure.
2. **Automated Cross-Platform Host Registration**: A unified Node setup script (`setup-host.mjs`) that automatically writes Chrome/Chromium/Brave Native Messaging manifests on Linux/macOS and executes `reg.exe` registry entries + generates `native-host.bat` on Windows.
3. **Deterministic Extension ID**: Pinning the extension public key in `extension/manifest.json` ensuring identical Extension IDs across unpacked developer builds and Chrome Web Store releases.
4. **Smart Python Bootstrapping & Multi-Client MCP Auto-Discovery**: Automated detection of Python 3.10+ / `uv`, creation of `.venv`, and automated configuration of Claude Desktop (macOS, Linux, Windows), Antigravity/Gemini CLI, and Cursor.
5. **Actionable Disconnection Diagnostics**: Self-healing `BrowserUnavailableError` providing actionable checklists when Chrome or the extension is not yet active.

## User Stories

1. As a developer on macOS, I want to run a single setup command so that Chrome Native Messaging manifests, the Python virtual environment, and Claude Desktop MCP configurations are created automatically.
2. As a developer on Windows, I want the setup script to register the Chrome Native Messaging host into the Windows Registry (`HKCU`) without needing administrator rights or manual registry editing.
3. As a developer on Windows, I want Chrome to execute the Native Messaging Host via an automated batch wrapper (`native-host.bat`) so that Node execution succeeds seamlessly without shebang errors.
4. As a developer on any OS, I want local IPC communication between the Python REPL and the Native Host to use the operating system's standard temporary directory (`%TEMP%` on Windows, `/tmp` or standard temp dir on POSIX) so that hardcoded path errors never occur.
5. As a developer loading the Chrome extension unpacked from GitHub, I want the Extension ID to be deterministic and identical to the Web Store build so that Native Messaging permissions work immediately without editing manifests.
6. As an AI Agent Driver, I want `BrowserUnavailableError` to provide clear, actionable troubleshooting steps (e.g., check Chrome is running, verify extension is enabled) when the browser is disconnected.
7. As a Claude Desktop user on Windows, I want the installer to detect `%APPDATA%\Claude\claude_desktop_config.json` and configure the Python REPL MCP server with proper Windows paths and executable arguments.
8. As a Claude Desktop user on macOS, I want the installer to detect `~/Library/Application Support/Claude/claude_desktop_config.json` and configure the MCP server seamlessly.
9. As a developer without `uv` pre-installed, I want the setup script to fall back to `python3 -m venv` / `py -m venv` so that installation succeeds without extra tool requirements.
10. As a developer without a compatible Python version, I want the setup script to fail fast with direct OS-specific install commands (e.g., `brew install python@3.11`, `winget install Python.Python.3.11`).
11. As a maintainer sharing the repository on GitHub, I want a clean `README.md` and automated setup script so that new contributors can start in under 60 seconds across all major operating systems.

## Implementation Decisions

### Cross-Platform IPC Seam
- **Socket Path Resolution**: Replace hardcoded `"/tmp/chrome_bridge.sock"` with dynamic platform resolution across Python and Node.
  - Python: `os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.sock")`
  - Node: `path.join(os.tmpdir(), "antigravity_chrome_bridge.sock")`
- **Abstraction Seam**: The Driver interface remains completely decoupled from IPC transport mechanics; socket errors continue to map cleanly to `BrowserUnavailableError`.

### Windows Native Messaging Host & Registry
- **Windows Executable Wrapper**: On `win32`, generate `native-host.bat` inside the project root pointing to `node "<project_dir>/native-host.mjs" %*`.
- **Windows Manifest**: Point `path` in the JSON manifest to `native-host.bat` on Windows, and `native-host.mjs` on POSIX.
- **Registry Injection**: On `win32`, execute `reg.exe add "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.antigravity.chrome_bridge" /ve /t REG_SZ /d "<path_to_manifest_json>" /f` (and corresponding keys for Brave, Chromium, and Edge).

### Extension Key Pinning
- **Deterministic ID**: Add a 2048-bit RSA public key `key` field to `extension/manifest.json` ensuring fixed ID `nbghhppoiigjbdjbhefiaijofpnhgepb`.

### Multi-Client MCP Discovery
- **Platform Matrix Config**:
  - Claude Desktop: Linux (`~/.config/Claude`), macOS (`~/Library/Application Support/Claude`), Windows (`%APPDATA%/Claude`).
  - Antigravity / Gemini CLI: `~/.agent/mcp_config.json` and `~/.gemini/antigravity-cli/mcp_config.json`.
  - Cursor: `~/.cursor/mcp.json` / workspace configuration.
- **Absolute Python Pathing**: Resolve `.venv/bin/python` (POSIX) or `.venv/Scripts/python.exe` (Windows) to avoid PATH inheritance issues when GUI apps launch MCP servers.

### Actionable Diagnostics
- **Sanitized Guidance**: Enrich `BrowserUnavailableError` with structured actionable tips without leaking raw internal transport stack traces.

## Testing Decisions

- **Testing External Behavior**: Tests must verify the public domain behavior and abstractions without coupling to internal OS quirks.
- **IPC Resolution Tests**: Unit tests in `tests/test_chrome_sdk.py` verifying dynamic socket path construction across OS environments (mocking `tempfile.gettempdir()` / `os.name`).
- **Host Setup Unit Tests**: Tests verifying manifest generation, path escaping (especially Windows backslashes in JSON), and platform branching.
- **Sanitization & Error Tests**: Expand `tests/test_zero_leakage.py` and `tests/test_diagnostics.py` to ensure enhanced `BrowserUnavailableError` messages remain completely free of raw OS/internal leakage.

## Out of Scope

- Chrome Web Store developer dashboard submission fees and manual review process (handled via documentation/manual submission).
- Firefox WebExtensions Native Messaging support (focus remains on Chromium-based browsers: Chrome, Brave, Edge, Chromium).
- Remote network browser automation over WebSockets/LAN (strictly local IPC for security).

## Further Notes

- Respects ADR 0001 (Cross-Platform IPC Transport & Native Host Registration) and ADR 0002 (Deterministic Extension Key Pinning & Hybrid Distribution).
- All changes maintain strict Zero Information Leakage guarantees in `CONTEXT.md`.
