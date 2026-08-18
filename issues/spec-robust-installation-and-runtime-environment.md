# Spec: Robust Cross-Platform Installation & Subagent Runtime Environment

**Label:** `ready-for-agent`  
**Parent Map:** [Map: Adaptive & Context-Aware Chrome Bridge Architecture](file:///home/shivansh/chrome-bridge/issues/map.md)

---

## Problem Statement

When users install, configure, and orchestrate Chrome Bridge across diverse desktop operating systems (macOS, Linux, Windows), browser packaging formats (native, Flatpak, Snap), and AI agent execution environments (subagents running in ambient Python vs isolated virtual environments):

1. **Runtime Directory Naming Mismatch:** Setup scripts install the persistent runtime to a hidden dotfile directory (`~/.chrome-bridge`), while agent skill instructions specify the non-dotted directory (`~/chrome-bridge`), causing spawned subagents to fail with `ModuleNotFoundError: No module named 'chrome_sdk'`.
2. **POSIX GUI Desktop `$PATH` Blindspot:** When Chrome is launched via GUI desktop launchers (macOS Dock/Spotlight, Linux application menus/systemd) rather than an interactive terminal session, it does not inherit shell profile environment variables (`.bashrc`, `.zshrc`). The direct `#!/usr/bin/env node` shebang fails to locate Node.js when installed via package managers (Homebrew on Apple Silicon, NVM, FNM, ASDF, or local user bins), leading to silent connection failure.
3. **Subagent Ambient Python & Dependency Disconnect:** When a subagent executes Python scripts or REPL commands without activating the virtual environment, it runs under the parent agent's ambient system Python and cannot locate third-party dependencies (such as websockets or rich) provisioned inside the runtime virtual environment.
4. **Sandboxed Linux Browser Native Manifest Blindspot:** Modern Linux distributions default to sandboxed Flatpak or Snap browser packages. Standard user configuration paths (`~/.config/...`) are invisible to sandboxed browsers, preventing them from locating the Native Messaging host manifest.
5. **Rigid Skill Source File Discovery:** The setup installer expects the source skill definition to reside at a single hardcoded path. If repository files are structured differently or packaged at root, the installer silently skips installing agent skills.

---

## Solution

A **Hardened Cross-Platform Installation & Zero-Assumption Subagent Runtime Architecture**:

- **Unified Multi-Path SDK Discovery:** Standardizes the canonical persistent installation directory to `~/.chrome-bridge` while making Python SDK bootstrapping resilient through multi-directory fallback resolution across active workspaces, `~/.chrome-bridge`, and legacy `~/chrome-bridge`.
- **POSIX Host Launcher Wrapper (`native-host.sh`):** Generates an executable shell wrapper script during setup that embeds the resolved Node binary path discovered during installation and includes fallback probes for standard package manager directories before invoking the native host script. The browser Native Messaging manifest points directly to this launcher script.
- **Ambient Virtualenv Site-Packages Discovery:** Automatically probes and injects virtual environment site-packages into the runtime `sys.path` via site package directory registration, allowing subagents running under ambient Python to import all necessary dependencies without manual virtualenv activation.
- **Comprehensive Sandboxed Browser Manifest Coverage:** Automatically detects and registers Native Messaging host manifests across both traditional and sandboxed Linux browser configurations (Flatpak and Snap for Google Chrome, Chromium, Brave, and Microsoft Edge).
- **Flexible Multi-Root Skill Source Resolver:** Employs a prioritized candidate locator to discover `SKILL.md` from multiple source layouts and reliably synchronizes the skill to all supported agent directories.

---

## User Stories

1. As an AI agent orchestrator spawning a fresh subagent, I want the subagent to import `chrome_sdk` without path errors, so that browser actions execute reliably regardless of whether the persistent runtime is at `~/.chrome-bridge` or `~/chrome-bridge`.
2. As a subagent executing Python code under ambient system Python, I want the virtual environment's site-packages to be automatically discovered and attached to `sys.path`, so that third-party runtime dependencies are always accessible without manual environment activation.
3. As a macOS user launching Google Chrome from the Dock, I want the Chrome extension to successfully connect to the native messaging host, so that the extension connects even though the GUI application did not inherit terminal shell profile `$PATH` variables.
4. As a macOS user using Homebrew on Apple Silicon (`/opt/homebrew/bin/node`), I want the native host launcher to locate my Node.js executable automatically, so that native messaging communication never fails.
5. As a developer using Node version managers (NVM, FNM, ASDF), I want the setup script to capture the active Node.js binary path into the launcher wrapper, so that Chrome can execute the native host without relying on system-wide node links.
6. As a Linux user running Google Chrome or Chromium via Flatpak, I want the setup script to register the Native Messaging manifest inside the Flatpak configuration directory, so that the sandboxed browser finds the host manifest.
7. As a Linux user running Brave or Microsoft Edge via Flatpak, I want the setup script to create the appropriate manifest files in their respective sandbox directories, so that alternative sandboxed browsers work out of the box.
8. As an Ubuntu Linux user running Chromium, Brave, or Edge via Snap packages, I want the installer to register manifests inside the Snap configuration trees, so that Snap sandbox boundaries do not prevent native messaging communication.
9. As a developer installing Chrome Bridge from various directory structures (root package, submodule, or repository clone), I want the installer to locate `SKILL.md` across multiple candidate locations, so that skills are always installed into agent directories.
10. As an Antigravity CLI user, I want the installer to register skills in all global and local agent skill directories (`.agent`, `.agents`, `.gemini/antigravity-cli`, and `.gemini/config`), so that the skill is immediately accessible in any agent workspace.
11. As a Windows user, I want the installer to maintain the existing `.bat` host wrapper and registry keys, so that cross-platform consistency is preserved.
12. As an AI assistant, I want the SDK bootstrap preamble in the skill definition to include directory probing and virtualenv site-packages registration, so that subagent code snippets are robust against execution context variations.
13. As a developer running diagnostics via the setup status command, I want the CLI status output to report on Flatpak, Snap, and traditional browser manifest registrations, so that I can easily verify host registration health.
14. As a continuous integration runner, I want setup scripts to handle missing sandbox directories gracefully without crashing, so that headless automated test pipelines pass cleanly.
15. As an agent controlling a browser tab, I want zero ambient environment leakage, so that runtime path adjustments do not corrupt the parent agent's workspace configuration.

---

## Implementation Decisions

### 1. Unified Directory Hierarchy & Multi-Path Bootstrap Strategy
- The persistent runtime directory is standardized to `~/.chrome-bridge`.
- The SDK bootstrap logic in skill preambles and client libraries probes candidate paths in order:
  1. Current working directory / active workspace root
  2. User home hidden runtime directory (`~/.chrome-bridge`)
  3. User home explicit directory (`~/chrome-bridge`)
- The first matching directory containing the client library is added to the head of `sys.path`.

### 2. POSIX Host Launcher Wrapper Architecture
- Setup generates an executable shell script `native-host.sh` in the runtime directory on POSIX systems (Linux and macOS), mirroring `native-host.bat` on Windows.
- The wrapper script:
  - Sets encoding environment variables (`PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`).
  - Contains the pinned absolute path of the Node.js executable captured at setup time.
  - Implements fallback probe logic checking standard locations (`/opt/homebrew/bin/node`, `/usr/local/bin/node`, `~/.nvm/versions/node/...`, `~/.fnm/current/bin/node`, `~/.asdf/shims/node`, `~/.local/bin/node`, `/usr/bin/node`) if the pinned binary has moved.
  - Forwards standard input/output streams to the native host script.
- The Native Messaging JSON manifest on POSIX systems configures its `path` property to point to `native-host.sh`.
- Executable permissions (`0755`) are automatically applied to both the shell wrapper and the underlying JavaScript file.

### 3. Ambient Virtualenv Site-Packages Auto-Discovery
- The client SDK, REPL engine, and MCP server initialization routines inspect the resolved runtime directory for an existing `.venv` folder.
- If a `.venv` directory exists:
  - On POSIX: Searches for `lib/python*/site-packages`.
  - On Windows: Searches for `Lib/site-packages`.
- Any matching site-packages directory is registered using Python's standard `site.addsitedir()`, ensuring all packages and `.pth` links are activated for ambient Python interpreters.

### 4. Sandboxed Browser Manifest Registration Matrix
- The installer manifest registration routine expands the target directory matrix:
  - **Traditional Linux:**
    - Google Chrome: `~/.config/google-chrome/NativeMessagingHosts`
    - Chromium: `~/.config/chromium/NativeMessagingHosts`
    - Brave: `~/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts`
    - Microsoft Edge: `~/.config/microsoft-edge/NativeMessagingHosts`
  - **Flatpak Linux:**
    - Google Chrome: `~/.var/app/com.google.Chrome/config/google-chrome/NativeMessagingHosts`
    - Chromium: `~/.var/app/org.chromium.Chromium/config/chromium/NativeMessagingHosts`
    - Brave: `~/.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/NativeMessagingHosts`
    - Microsoft Edge: `~/.var/app/com.microsoft.Edge/config/microsoft-edge/NativeMessagingHosts`
  - **Snap Linux:**
    - Chromium: `~/snap/chromium/current/.config/chromium/NativeMessagingHosts`
    - Brave: `~/snap/brave/current/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts`
    - Microsoft Edge: `~/snap/edge/current/.config/microsoft-edge/NativeMessagingHosts`
  - **macOS:**
    - Standard Library Application Support directories for Chrome, Chromium, Brave, and Edge.
  - **Windows:**
    - Registry keys under `HKCU\Software\...` for Chrome, Brave, Edge, and Chromium.

### 5. Multi-Candidate Skill Source Discovery
- The setup installer searches a prioritized array of source paths for `SKILL.md`:
  1. `<INSTALL_DIR>/.agents/skills/chrome-bridge/SKILL.md`
  2. `<INSTALL_DIR>/SKILL.md`
  3. `<INSTALL_DIR>/skills/chrome-bridge/SKILL.md`
  4. `<SCRIPT_DIR>/.agents/skills/chrome-bridge/SKILL.md`
  5. `<SCRIPT_DIR>/SKILL.md`
- The first existing file is copied to all destination agent skill paths.

---

## Testing Decisions

### Good Test Principles
- Tests must verify external observable behavior (file generation, executable permissions, path resolution outputs, manifest validity) rather than private implementation details.
- Environment path probing tests must test behavior across mock directories representing different OS and sandbox configurations.

### Tested Modules
- **Setup Host Generator:** Verify that `native-host.sh` is generated on POSIX, contains valid shell syntax and path probes, and has executable file permissions.
- **Native Manifest Path:** Verify that the generated Native Messaging manifest points to `native-host.sh` on POSIX and `native-host.bat` on Windows.
- **Virtualenv Site-Packages Discovery:** Verify that the SDK initialization helper locates `.venv` and adds its site-packages to `sys.path`.
- **Directory Fallback Resolver:** Verify that the runtime directory discovery correctly falls back through the candidate list.
- **Skill Source Resolver:** Verify that `SKILL.md` is discovered from root and nested directories.

### Prior Art
- `tests/test_chrome_sdk.py` (Client initialization and environment setup).
- `tests/test_repl_engine.py` (REPL runtime path injection and execution isolation).
- `tests/test_zero_leakage.py` (Cleanup and environment isolation).

---

## Out of Scope

- Managing system-level browser policy installations requiring root/administrator permissions (`/etc/opt/chrome/native-messaging-hosts` or system registry `HKLM`).
- Automatic Flatpak or Snap browser application installation (only manifest registration for existing/future sandbox directories is in scope).
- Native host compilation into standalone binary binaries (Node.js runtime remains standard).

---

## Further Notes

- The POSIX launcher wrapper approach avoids modifying user shell configuration files (`~/.bashrc`, `~/.zshrc`) while ensuring GUI browser launches have guaranteed access to Node.js.
- All changes are completely non-destructive and backward compatible with existing repository workspaces and installations.
