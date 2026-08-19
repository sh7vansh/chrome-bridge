#!/usr/bin/env python3
"""Chrome Bridge - Pure Python Host Registration & Setup CLI.

Standard library only. Manages cross-platform native messaging manifest registration,
launcher wrapper scripts, agent skill deployment, and MCP client configurations
(Claude Code, Antigravity, Cursor, Claude Desktop).
"""

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import atexit
import threading
import time

HOST_NAME = "com.chrome_bridge.native"
EXTENSION_ID = "nbghhppoiigjbdjbhefiaijofpnhgepb"
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


class SpinnerContext:
    """Threaded ANSI animated Braille spinner context manager."""

    def __init__(self, ui: "TerminalUI", message: str):
        self.ui = ui
        self.message = message
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._completed = False

    def __enter__(self) -> "SpinnerContext":
        if self.ui.interactive:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self.ui._hide_cursor()
            self._thread.start()
        else:
            self.ui.stream.write(f"  ... {self.message}\n")
            self.ui.stream.flush()
        return self

    def _spin(self) -> None:
        idx = 0
        frames = self.ui.SPINNER_FRAMES
        while not self._stop_event.is_set():
            frame = frames[idx % len(frames)]
            self.ui.stream.write(f"\r  {self.ui.cyan(frame)} {self.message}\033[K")
            self.ui.stream.flush()
            idx += 1
            time.sleep(0.08)

    def ok(self, final_msg: Optional[str] = None) -> None:
        self._finish(self.ui.green("✓"), final_msg or self.message)

    def fail(self, final_msg: Optional[str] = None) -> None:
        self._finish(self.ui.red("✗"), final_msg or self.message)

    def warn(self, final_msg: Optional[str] = None) -> None:
        self._finish(self.ui.yellow("⚠️"), final_msg or self.message)

    def skip(self, final_msg: Optional[str] = None) -> None:
        self._finish(self.ui.dim("○"), final_msg or self.message)

    def _finish(self, symbol: str, text: str) -> None:
        if self._completed:
            return
        self._completed = True
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.2)
        if self.ui.interactive:
            self.ui.stream.write(f"\r  {symbol} {text}\033[K\n")
            self.ui._show_cursor()
        else:
            self.ui.stream.write(f"  {symbol} {text}\n")
        self.ui.stream.flush()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self._completed:
            if exc_type is not None:
                self.fail(f"{self.message} (failed: {exc_val})")
            else:
                self.ok()
        self.ui._show_cursor()


class TerminalUI:
    """Pure-Python zero-dependency live terminal UI and rendering engine."""

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    ASCII_SPINNER_FRAMES = ["|", "/", "-", "\\"]

    def __init__(
        self,
        force_color: Optional[bool] = None,
        interactive: Optional[bool] = None,
        stream: Optional[Any] = None,
    ):
        self.stream = stream or sys.stdout
        is_tty = hasattr(self.stream, "isatty") and self.stream.isatty()

        no_color_env = bool(os.environ.get("NO_COLOR"))
        ci_env = bool(os.environ.get("CI"))
        dumb_term = os.environ.get("TERM") == "dumb"

        if force_color is not None:
            self.supports_color = force_color
        else:
            self.supports_color = not no_color_env and (
                is_tty or os.environ.get("FORCE_COLOR") == "1"
            )

        if interactive is not None:
            self.interactive = interactive
        else:
            self.interactive = is_tty and not ci_env and not dumb_term

        try:
            encoding = getattr(self.stream, "encoding", "utf-8") or "utf-8"
            self.supports_unicode = "utf" in encoding.lower()
        except Exception:
            self.supports_unicode = True

        if not self.supports_unicode:
            self.SPINNER_FRAMES = self.ASCII_SPINNER_FRAMES

        self._cursor_hidden = False
        atexit.register(self._show_cursor)

    def _hide_cursor(self) -> None:
        if self.interactive and not self._cursor_hidden:
            self.stream.write("\033[?25l")
            self.stream.flush()
            self._cursor_hidden = True

    def _show_cursor(self) -> None:
        if self.interactive and self._cursor_hidden:
            self.stream.write("\033[?25h")
            self.stream.flush()
            self._cursor_hidden = False

    def colorize(self, code: str, text: str) -> str:
        if not self.supports_color:
            return str(text)
        return f"\033[{code}m{text}\033[0m"

    def bold(self, text: str) -> str:
        return self.colorize("1", text)

    def dim(self, text: str) -> str:
        return self.colorize("2", text)

    def cyan(self, text: str) -> str:
        return self.colorize("36", text)

    def green(self, text: str) -> str:
        return self.colorize("32", text)

    def yellow(self, text: str) -> str:
        return self.colorize("33", text)

    def red(self, text: str) -> str:
        return self.colorize("31", text)

    def magenta(self, text: str) -> str:
        return self.colorize("35", text)

    def blue(self, text: str) -> str:
        return self.colorize("34", text)

    def badge_done(self, label: str = "DONE") -> str:
        return f"{self.green('✓')} {self.bold(label)}" if self.supports_unicode else f"[{self.green(label)}]"

    def badge_fail(self, label: str = "FAIL") -> str:
        return f"{self.red('✗')} {self.bold(label)}" if self.supports_unicode else f"[{self.red(label)}]"

    def badge_warn(self, label: str = "WARN") -> str:
        return f"{self.yellow('⚠️')} {self.bold(label)}" if self.supports_unicode else f"[{self.yellow(label)}]"

    def spinner(self, message: str) -> SpinnerContext:
        return SpinnerContext(self, message)

    def card(self, title: str, items: List[Tuple[str, str]]) -> str:
        lines = [self.bold(self.cyan(f"╭── {title} ───────────────────────────────────────"))]
        max_k = max((len(k) for k, _ in items), default=10)
        for k, v in items:
            lines.append(f"│  • {self.bold(k.ljust(max_k))}: {v}")
        lines.append(self.bold(self.cyan("╰───────────────────────────────────────────────────")))
        return "\n".join(lines)

    def banner(self, title: str = "Chrome Bridge — Smart Live Assistant") -> None:
        self.stream.write(f"\n{self.bold(self.cyan('================================================================'))}\n")
        self.stream.write(f"{self.bold(self.cyan(f'   🌐 {title}'))}\n")
        self.stream.write(f"{self.bold(self.cyan('================================================================'))}\n\n")
        self.stream.flush()


# Global default terminal UI instance
ui = TerminalUI()
bold = ui.bold
dim = ui.dim
cyan = ui.cyan
green = ui.green
yellow = ui.yellow
red = ui.red
banner = ui.banner


def resolve_home_dir() -> Path:
    """Resolve user home directory respecting HOME / USERPROFILE env overrides."""
    if "HOME" in os.environ:
        return Path(os.environ["HOME"])
    if "USERPROFILE" in os.environ:
        return Path(os.environ["USERPROFILE"])
    return Path.home()


def resolve_install_dir(target_arg: Optional[str], is_dev: bool) -> Path:
    """Determine installation root directory."""
    if target_arg:
        return Path(target_arg).resolve()
    if is_dev:
        return Path(__file__).resolve().parent
    return resolve_home_dir() / ".chrome-bridge"


def resolve_extension_dir(install_dir: Path, source_dir: Optional[Path] = None) -> Path:
    """Resolve the unpacked Chrome extension directory path."""
    inst_ext = install_dir / "extension"
    if inst_ext.exists():
        return inst_ext.resolve()

    src = source_dir or Path(__file__).resolve().parent
    src_ext = src / "extension"
    if src_ext.exists():
        return src_ext.resolve()

    return inst_ext.resolve()


def resolve_python_executable(install_dir: Path) -> str:
    """Find the most appropriate Python executable."""
    venv_dir = install_dir / ".venv"
    if IS_WINDOWS:
        venv_py = venv_dir / "Scripts" / "python.exe"
    else:
        venv_py = venv_dir / "bin" / "python3"

    if venv_py.exists():
        return str(venv_py)

    # Check if current running python is suitable
    if sys.version_info >= (3, 10):
        return sys.executable

    # Fallback search
    for cand in ("python3", "python", "py"):
        found = shutil.which(cand)
        if found:
            return found

    return sys.executable or "python3"


def sync_runtime_files(source_dir: Path, install_dir: Path, quiet: bool = False) -> None:
    """Copy runtime scripts and assets when target differs from source directory."""
    if source_dir.resolve() == install_dir.resolve():
        if not quiet:
            print(f"  {green('✓')} Running directly from source directory.")
        return

    install_dir.mkdir(parents=True, exist_ok=True)
    runtime_files = [
        "native_host.py",
        "mcp_server.py",
        "repl_engine.py",
        "chrome_sdk.py",
        "setup_host.py",
        "requirements.txt",
        "pyproject.toml",
    ]

    for fname in runtime_files:
        src = source_dir / fname
        dst = install_dir / fname
        if src.exists():
            shutil.copy2(src, dst)
            if not quiet:
                size = dst.stat().st_size
                print(f"  {green('✓')} Synced {bold(fname)} {dim(f'({size} bytes)')}")

    # Copy directories if present
    for dname in (".agents", "extension", "skills"):
        src_dir = source_dir / dname
        dst_dir = install_dir / dname
        if src_dir.exists():
            if dst_dir.exists():
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
            if not quiet:
                print(f"  {green('✓')} Synced directory {bold(dname + '/')}")


def generate_host_launcher(install_dir: Path, python_exec: str, quiet: bool = False) -> Path:
    """Generate executable launcher wrapper for Chrome Native Messaging Host."""
    native_host_py = (install_dir / "native_host.py").resolve()

    if IS_WINDOWS:
        bat_path = install_dir / "native-host.bat"
        content = (
            "@echo off\r\n"
            "setlocal\r\n"
            "chcp 65001 >nul 2>&1\r\n"
            "set PYTHONIOENCODING=utf-8\r\n"
            "set PYTHONUTF8=1\r\n"
            f'"{python_exec}" "{native_host_py}" %*\r\n'
        )
        bat_path.write_text(content, encoding="utf-8")
        if not quiet:
            print(f"  {green('✓')} Generated Windows Host Batch Wrapper: {bat_path}")
        return bat_path
    else:
        sh_path = install_dir / "native-host.sh"
        sh_content = f"""#!/bin/sh
# Chrome Bridge Native Host POSIX Launcher Wrapper
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

# Pinned Python binary captured during setup
PINNED_PYTHON="{python_exec}"

if [ -x "$PINNED_PYTHON" ]; then
  PY_BIN="$PINNED_PYTHON"
else
  # Fallback probes for uv, Homebrew, venv, and standard system paths
  PY_BIN=""
  for candidate in \\
    "$HOME/.local/bin/uv" \\
    "/opt/homebrew/bin/python3" \\
    "/usr/local/bin/python3" \\
    "$HOME/.cargo/bin/uv" \\
    "$HOME/.local/bin/python3" \\
    "/usr/bin/python3"; do
    if [ -x "$candidate" ]; then
      PY_BIN="$candidate"
      break
    fi
  done
  if [ -z "$PY_BIN" ]; then
    PY_BIN="$(command -v python3 2>/dev/null || which python3 2>/dev/null || echo "python3")"
  fi
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$PY_BIN" "$SCRIPT_DIR/native_host.py" "$@"
"""
        sh_path.write_text(sh_content, encoding="utf-8")
        # Ensure executable permissions (0755)
        sh_path.chmod(sh_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        if (install_dir / "native_host.py").exists():
            nh_py = install_dir / "native_host.py"
            nh_py.chmod(nh_py.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        if not quiet:
            print(f"  {green('✓')} Generated POSIX Host Shell Wrapper (0755): {sh_path}")
        return sh_path


PROCDIR_OVERRIDE: Optional[Path] = None


class BrowserInfo:
    """Descriptor for a detected browser target."""

    def __init__(
        self,
        name: str,
        manifest_path: Path,
        is_installed: bool,
        is_running: bool = False,
        browser_type: str = "system",
    ):
        self.name = name
        self.manifest_path = manifest_path
        self.is_installed = is_installed
        self.is_running = is_running
        self.browser_type = browser_type


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


def detect_running_browsers() -> List[str]:
    """Detect currently running Chromium-based browser processes."""
    running: List[str] = []

    if IS_LINUX:
        proc_dir = PROCDIR_OVERRIDE or Path("/proc")
        if proc_dir.exists():
            signatures = {
                "chrome": "Google Chrome",
                "google-chrome": "Google Chrome",
                "brave": "Brave Browser",
                "brave-browser": "Brave Browser",
                "msedge": "Microsoft Edge",
                "chromium": "Chromium",
                "vivaldi": "Vivaldi",
                "arc": "Arc",
            }
            try:
                for entry in proc_dir.iterdir():
                    if entry.name.isdigit():
                        comm_file = entry / "comm"
                        try:
                            if comm_file.exists():
                                comm = comm_file.read_text(encoding="utf-8", errors="ignore").strip().lower()
                                for sig, bname in signatures.items():
                                    if sig in comm and bname not in running:
                                        running.append(bname)
                        except Exception:
                            continue
            except Exception:
                pass
    elif IS_MAC:
        try:
            res = subprocess.run(["ps", "-A", "-o", "comm="], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
            out = res.stdout.lower()
            if "google chrome" in out:
                running.append("Google Chrome")
            if "brave" in out:
                running.append("Brave Browser")
            if "edge" in out or "microsoft edge" in out:
                running.append("Microsoft Edge")
            if "chromium" in out:
                running.append("Chromium")
            if "arc" in out:
                running.append("Arc")
            if "vivaldi" in out:
                running.append("Vivaldi")
        except Exception:
            pass
    elif IS_WINDOWS:
        try:
            res = subprocess.run(["tasklist", "/nh", "/fo", "csv"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
            out = res.stdout.lower()
            if "chrome.exe" in out:
                running.append("Google Chrome")
            if "brave.exe" in out:
                running.append("Brave Browser")
            if "msedge.exe" in out:
                running.append("Microsoft Edge")
            if "chromium.exe" in out:
                running.append("Chromium")
            if "vivaldi.exe" in out:
                running.append("Vivaldi")
        except Exception:
            pass

    return running


def get_browser_manifest_targets(home_dir: Path) -> List[Tuple[str, Path]]:
    """Return all standard native messaging manifest file paths for the current platform."""
    targets: List[Tuple[str, Path]] = []

    if IS_LINUX:
        targets.extend([
            # Traditional Linux
            ("Google Chrome", home_dir / ".config" / "google-chrome" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Chromium", home_dir / ".config" / "chromium" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Brave Browser", home_dir / ".config" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Microsoft Edge", home_dir / ".config" / "microsoft-edge" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Vivaldi", home_dir / ".config" / "vivaldi" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Arc", home_dir / ".config" / "arc" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            # Flatpak Linux
            ("Google Chrome (Flatpak)", home_dir / ".var" / "app" / "com.google.Chrome" / "config" / "google-chrome" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Chromium (Flatpak)", home_dir / ".var" / "app" / "org.chromium.Chromium" / "config" / "chromium" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Brave Browser (Flatpak)", home_dir / ".var" / "app" / "com.brave.Browser" / "config" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Microsoft Edge (Flatpak)", home_dir / ".var" / "app" / "com.microsoft.Edge" / "config" / "microsoft-edge" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            # Snap Linux
            ("Chromium (Snap)", home_dir / "snap" / "chromium" / "current" / ".config" / "chromium" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Brave Browser (Snap)", home_dir / "snap" / "brave" / "current" / ".config" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Microsoft Edge (Snap)", home_dir / "snap" / "edge" / "current" / ".config" / "microsoft-edge" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
        ])
    elif IS_MAC:
        app_support = home_dir / "Library" / "Application Support"
        targets.extend([
            ("Google Chrome (macOS)", app_support / "Google" / "Chrome" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Chromium (macOS)", app_support / "Chromium" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Brave (macOS)", app_support / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Microsoft Edge (macOS)", app_support / "Microsoft Edge" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
        ])
    return targets


def detect_installed_browsers(home_dir: Path) -> List[BrowserInfo]:
    """Inspect and classify installed browsers and manifest paths."""
    running_names = detect_running_browsers()
    manifest_targets = get_browser_manifest_targets(home_dir)
    results: List[BrowserInfo] = []

    for name, manifest_path in manifest_targets:
        is_inst = False
        b_type = "system"
        if "Flatpak" in name:
            b_type = "flatpak"
            app_root = manifest_path.parent.parent.parent
            is_inst = app_root.exists()
        elif "Snap" in name:
            b_type = "snap"
            snap_root = manifest_path.parent.parent.parent.parent
            is_inst = snap_root.exists()
        elif IS_WINDOWS:
            b_type = "winreg"
            is_inst = True
        else:
            config_parent = manifest_path.parent.parent
            is_inst = config_parent.exists()
            if not is_inst:
                bin_names = {
                    "Google Chrome": ["google-chrome", "google-chrome-stable", "chrome"],
                    "Chromium": ["chromium", "chromium-browser"],
                    "Brave Browser": ["brave-browser", "brave"],
                    "Microsoft Edge": ["microsoft-edge", "microsoft-edge-stable"],
                    "Vivaldi": ["vivaldi", "vivaldi-stable"],
                    "Arc": ["arc"],
                }
                for b_key, b_bins in bin_names.items():
                    if b_key in name:
                        if any(shutil.which(b) for b in b_bins):
                            is_inst = True
                            break

        is_run = any(r_name.lower() in name.lower() for r_name in running_names)
        results.append(BrowserInfo(
            name=name,
            manifest_path=manifest_path,
            is_installed=is_inst,
            is_running=is_run,
            browser_type=b_type,
        ))

    return results


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
    ]
    if IS_MAC:
        client_defs.append(("Claude Desktop (macOS)", home_dir / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"))
    if app_data:
        client_defs.append(("Claude Desktop (Windows)", Path(app_data) / "Claude" / "claude_desktop_config.json"))

    results: List[MCPClientInfo] = []
    for name, path in client_defs:
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


def register_browser_manifests(launcher_path: Path, install_dir: Path, home_dir: Path, quiet: bool = False) -> None:
    """Write browser native messaging manifest JSON and register Windows registry keys if on Windows."""
    manifest_data = {
        "name": HOST_NAME,
        "description": "Chrome Bridge Native Messaging Host for AI Procedural Automation",
        "path": str(launcher_path),
        "type": "stdio",
        "allowed_origins": [
            f"chrome-extension://{EXTENSION_ID}/"
        ],
    }
    manifest_json = json.dumps(manifest_data, indent=2) + "\n"

    if IS_WINDOWS:
        manifest_path = install_dir / f"{HOST_NAME}.json"
        manifest_path.write_text(manifest_json, encoding="utf-8")
        if not quiet:
            print(f"  {green('✓')} Wrote Windows Host Manifest: {manifest_path}")

        reg_subkeys = [
            rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}",
            rf"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\{HOST_NAME}",
            rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST_NAME}",
            rf"Software\Chromium\NativeMessagingHosts\{HOST_NAME}",
        ]
        try:
            import winreg
            for subkey in reg_subkeys:
                try:
                    k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, subkey)
                    winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(manifest_path))
                    winreg.CloseKey(k)
                    if not quiet:
                        print(f"  {green('✓')} Registered Windows Registry Key: {dim(subkey)}")
                except Exception:
                    pass
        except (ImportError, Exception):
            for subkey in reg_subkeys:
                try:
                    full_key = f"HKCU\\{subkey}"
                    subprocess.run(
                        ["reg.exe", "add", full_key, "/ve", "/t", "REG_SZ", "/d", str(manifest_path), "/f"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    if not quiet:
                        print(f"  {green('✓')} Registered Windows Registry Key: {dim(full_key)}")
                except Exception:
                    pass
    else:
        targets = get_browser_manifest_targets(home_dir)
        for browser_name, target_file in targets:
            try:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(manifest_json, encoding="utf-8")
                if not quiet:
                    print(f"  {green('✓')} Configured {bold(browser_name)} manifest: {dim(str(target_file))}")
            except Exception:
                pass


def install_agent_skill(install_dir: Path, source_dir: Path, home_dir: Path, quiet: bool = False) -> None:
    """Discover and install SKILL.md into global and local agent skill paths."""
    candidates = [
        install_dir / ".agents" / "skills" / "chrome-bridge" / "SKILL.md",
        install_dir / "SKILL.md",
        install_dir / "skills" / "chrome-bridge" / "SKILL.md",
        source_dir / ".agents" / "skills" / "chrome-bridge" / "SKILL.md",
        source_dir / "SKILL.md",
        source_dir / "skills" / "chrome-bridge" / "SKILL.md",
    ]

    skill_source: Optional[Path] = None
    for cand in candidates:
        if cand.exists():
            skill_source = cand
            break

    if not skill_source:
        if not quiet:
            print(f"  {yellow('⚠️ Skill file not found across candidate paths. Skipping skill copy.')}")
        return

    if not quiet:
        print(f"  {cyan('↳ Resolved skill source:')} {skill_source}")

    dest_dirs = [
        ("Antigravity Global Agent (.agents)", home_dir / ".agents" / "skills" / "chrome-bridge"),
        ("Antigravity Global Agent (.agent)", home_dir / ".agent" / "skills" / "chrome-bridge"),
        ("Gemini CLI Agent", home_dir / ".gemini" / "antigravity-cli" / "skills" / "chrome-bridge"),
        ("Gemini Config Skills", home_dir / ".gemini" / "config" / "skills" / "chrome-bridge"),
    ]

    for label, dest_dir in dest_dirs:
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(skill_source, dest_dir / "SKILL.md")
            if not quiet:
                print(f"  {green('✓')} Installed for {bold(label)}: {dim(str(dest_dir / 'SKILL.md'))}")
        except Exception as err:
            if not quiet:
                print(f"  {yellow(f'⚠️ Could not install skill to {dest_dir}:')} {err}")


def update_mcp_client_config(
    file_path: Path,
    client_name: str,
    command: str,
    args: List[str],
    quiet: bool = False,
) -> bool:
    """Non-destructively upsert chrome-bridge entry in an MCP client configuration file."""
    try:
        config: Dict[str, Any] = {"mcpServers": {}}
        if file_path.exists():
            try:
                raw = file_path.read_text(encoding="utf-8")
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    config = loaded
                if "mcpServers" not in config or not isinstance(config["mcpServers"], dict):
                    config["mcpServers"] = {}
            except Exception:
                if not quiet:
                    print(f"  {yellow(f'⚠️ Could not parse JSON in {file_path}, skipping...')}")
                return False
        else:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        config["mcpServers"]["chrome-bridge"] = {
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
    """Update MCP configurations across Claude Code, Antigravity, Claude Desktop, and Cursor."""
    if is_dev:
        mcp_script = (install_dir / "mcp_server.py").resolve()
        command = python_exec
        args = [str(mcp_script)]
    else:
        command = "uvx"
        args = ["--refresh", "antigravity-chrome-bridge", "mcp"]

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


def run_setup(args: argparse.Namespace) -> int:
    """Execute standard setup workflow with live terminal UI and discovery prober."""
    source_dir = Path(__file__).resolve().parent
    home_dir = resolve_home_dir()
    install_dir = resolve_install_dir(args.target, bool(getattr(args, "dev", False)))
    quiet = args.quiet

    if not quiet:
        banner("Chrome Bridge 2.0 — Pure Python Live Setup Assistant")
        print(ui.card("Execution & System Context", [
            ("Operating System", f"{platform.system()} ({platform.machine()})"),
            ("Python Runtime", f"{sys.version.split()[0]} ({sys.executable})"),
            ("Target Directory", str(install_dir)),
            ("Extension ID", EXTENSION_ID),
        ]))
        print()

    # Step 1: Synchronize runtime files
    with ui.spinner("Synchronizing runtime files and assets...") as sp:
        sync_runtime_files(source_dir, install_dir, quiet=True)
        sp.ok(f"Runtime files synchronized to {install_dir}")

    # Step 2: Resolve Python executable
    with ui.spinner("Resolving Python runtime environment...") as sp:
        python_exec = resolve_python_executable(install_dir)
        sp.ok(f"Selected Python: {python_exec}")

    # Step 3: Register Native Messaging Manifests
    with ui.spinner("Registering Chrome Native Messaging Host manifests...") as sp:
        launcher_path = generate_host_launcher(install_dir, python_exec, quiet=True)
        register_browser_manifests(launcher_path, install_dir, home_dir, quiet=True)
        browsers = detect_installed_browsers(home_dir)
        configured_browsers = [b.name for b in browsers if b.manifest_path.exists()]
        sp.ok(f"Configured {len(configured_browsers)} browser manifest(s)")

    # Step 4: Install Agent Skill
    with ui.spinner("Installing Agent Skill (chrome-bridge)...") as sp:
        install_agent_skill(install_dir, source_dir, home_dir, quiet=quiet)
        sp.ok("Agent skill deployed to Antigravity & Gemini config directories")

    # Step 5: Configure MCP Clients
    with ui.spinner("Configuring AI Agent Model Context Protocol (MCP) clients...") as sp:
        is_dev = bool(getattr(args, "dev", False))
        configure_all_mcp_clients(install_dir, home_dir, python_exec, is_dev=is_dev, quiet=True)
        clients = detect_mcp_clients(home_dir)
        configured_clients = [c.name for c in clients if c.is_configured]
        sp.ok(f"Configured {len(configured_clients)} MCP client(s): {', '.join(configured_clients)}")

    if not quiet:
        ext_dir = resolve_extension_dir(install_dir, source_dir)
        print()
        print(ui.card("Setup Summary & Ready State", [
            ("Status", ui.green("INSTALLATION READY")),
            ("Browsers", ", ".join(configured_browsers) if configured_browsers else "Default system paths"),
            ("MCP Clients", ", ".join(configured_clients) if configured_clients else "None configured"),
            ("Extension Path", str(ext_dir)),
        ]))
        print()
        print(bold("🧩 EXTENSION INSTALLATION INSTRUCTIONS:"))
        print(f"  1. Open Google Chrome and navigate to: {bold(cyan('chrome://extensions/'))}")
        print(f"  2. Enable {bold('Developer mode')} (toggle in the top-right corner).")
        print(f"  3. Click {bold('Load unpacked')} (top-left) and select the extension folder:")
        print(f"     👉 {bold(green(str(ext_dir)))}")
        print(f"  4. Click the {bold(cyan('Chrome Bridge'))} icon in your Chrome toolbar to connect.\n")

    # Step 6: Live Handshake Verification Loop
    if not quiet and not getattr(args, "no_listen", False):
        print(bold("📡 LIVE EXTENSION VERIFICATION:"))
        timeout = float(getattr(args, "timeout", 15.0) or 15.0)
        wait_for_extension_handshake(timeout_sec=timeout)

    return 0
def simulate_native_host(
    python_exec: str,
    host_script: Path,
) -> Tuple[bool, str, float]:
    """Launch native_host.py in a subprocess, verify stdio length-prefixed protocol, and measure latency."""
    t0 = time.perf_counter()
    try:
        proc = subprocess.Popen(
            [python_exec, str(host_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        assert proc.stdout is not None
        header = proc.stdout.read(4)
        if len(header) < 4:
            proc.kill()
            return False, "Failed to read 4-byte header from native host", 0.0

        import struct
        msg_len = struct.unpack("<I", header)[0]
        payload = proc.stdout.read(msg_len)
        data = json.loads(payload.decode("utf-8"))

        t1 = time.perf_counter()
        latency_ms = (t1 - t0) * 1000.0

        proc.kill()
        proc.wait(timeout=1.0)

        # Cleanup residual socket / port endpoints created during simulation
        import tempfile
        for temp_name in ("antigravity_chrome_bridge.sock", "antigravity_chrome_bridge.port"):
            t_path = Path(tempfile.gettempdir()) / temp_name
            if t_path.exists():
                try:
                    t_path.unlink()
                except Exception:
                    pass

        if data.get("event") == "host_ready":
            return True, f"Native host operational ({latency_ms:.1f}ms launch latency)", latency_ms
        return True, f"Received response: {data}", latency_ms
    except Exception as e:
        return False, f"Simulation failed: {e}", 0.0


def wait_for_extension_handshake(
    timeout_sec: float = 15.0,
    stream: Optional[Any] = None,
    force_non_interactive: bool = False,
) -> Optional[Dict[str, Any]]:
    """Live polling loop waiting for Chrome extension to connect to local IPC endpoint."""
    target_stream = stream or sys.stdout
    interactive = (hasattr(target_stream, "isatty") and target_stream.isatty()) and not force_non_interactive
    local_ui = TerminalUI(stream=target_stream, interactive=interactive)

    import tempfile
    import socket

    sock_path = Path(tempfile.gettempdir()) / "antigravity_chrome_bridge.sock"
    port_path = Path(tempfile.gettempdir()) / "antigravity_chrome_bridge.port"

    start_time = time.time()
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    frame_idx = 0

    if interactive:
        local_ui._hide_cursor()

    try:
        while time.time() - start_time < timeout_sec:
            remaining = max(0, int(timeout_sec - (time.time() - start_time)))

            active_endpoint = None
            if IS_WINDOWS and port_path.exists():
                try:
                    port = int(port_path.read_text(encoding="utf-8").strip())
                    active_endpoint = ("tcp", port)
                except Exception:
                    pass
            elif not IS_WINDOWS and sock_path.exists():
                active_endpoint = ("unix", str(sock_path))

            if active_endpoint:
                try:
                    if active_endpoint[0] == "tcp":
                        s = socket.create_connection(("127.0.0.1", active_endpoint[1]), timeout=1.0)
                    else:
                        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        s.settimeout(1.0)
                        s.connect(active_endpoint[1])

                    with s:
                        ping_req = json.dumps({"id": 1, "action": "ping"}).encode("utf-8") + b"\n"
                        s.sendall(ping_req)
                        raw_resp = s.recv(65536)
                        if raw_resp:
                            resp = json.loads(raw_resp.decode("utf-8").strip().split("\n")[0])
                            if interactive:
                                local_ui.stream.write(f"\r  {local_ui.green('✓')} {local_ui.bold('Live Chrome Extension Handshake Captured!')}\033[K\n")
                            else:
                                local_ui.stream.write(f"  ✓ Live Chrome Extension Handshake Captured!\n")
                            local_ui.stream.flush()
                            return resp
                except Exception:
                    pass

            if interactive:
                frame = frames[frame_idx % len(frames)]
                local_ui.stream.write(
                    f"\r  {local_ui.cyan(frame)} Waiting for Chrome Extension connection... {local_ui.dim(f'({remaining}s remaining)')}\033[K"
                )
                local_ui.stream.flush()
                frame_idx += 1
            time.sleep(0.25)

        if interactive:
            local_ui.stream.write(f"\r  {local_ui.yellow('○')} Extension connection listener timed out (host will activate when Chrome opens).\033[K\n")
        else:
            local_ui.stream.write(f"  ○ Extension connection listener timed out (host will activate when Chrome opens).\n")
        local_ui.stream.flush()
        return None
    finally:
        if interactive:
            local_ui._show_cursor()


def check_stale_ipc(auto_fix: bool = False) -> List[Dict[str, Any]]:
    """Check for orphaned or unresponsive socket and port files."""
    issues = []
    import tempfile
    import socket

    sock_path = Path(tempfile.gettempdir()) / "antigravity_chrome_bridge.sock"
    port_path = Path(tempfile.gettempdir()) / "antigravity_chrome_bridge.port"

    if not IS_WINDOWS and sock_path.exists():
        is_responsive = False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(str(sock_path))
                is_responsive = True
        except Exception:
            is_responsive = False

        if not is_responsive:
            fixed = False
            if auto_fix:
                try:
                    sock_path.unlink()
                    fixed = True
                except Exception:
                    pass
            issues.append({
                "type": "stale_ipc",
                "title": f"Stale IPC Unix socket found: {sock_path}",
                "detail": "Socket file exists but is not accepting connections (orphaned from dead host).",
                "fixed": fixed,
            })

    if IS_WINDOWS and port_path.exists():
        is_responsive = False
        try:
            port = int(port_path.read_text(encoding="utf-8").strip())
            with socket.create_connection(("127.0.0.1", port), timeout=0.5) as s:
                is_responsive = True
        except Exception:
            is_responsive = False

        if not is_responsive:
            fixed = False
            if auto_fix:
                try:
                    port_path.unlink()
                    fixed = True
                except Exception:
                    pass
            issues.append({
                "type": "stale_ipc",
                "title": f"Stale IPC TCP port file found: {port_path}",
                "detail": "Port file exists but port is not accepting connections.",
                "fixed": fixed,
            })

    return issues


def check_file_permissions(install_dir: Path, auto_fix: bool = False) -> List[Dict[str, Any]]:
    """Verify executable permissions on POSIX launcher scripts."""
    issues = []
    if IS_WINDOWS:
        return issues

    targets = [
        install_dir / "native-host.sh",
        install_dir / "native_host.py",
    ]

    for p in targets:
        if p.exists():
            st = p.stat()
            if not (st.st_mode & stat.S_IXUSR):
                fixed = False
                if auto_fix:
                    try:
                        p.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
                        fixed = True
                    except Exception:
                        pass
                issues.append({
                    "type": "permission",
                    "title": f"Missing executable permission on {p.name}",
                    "detail": f"File {p} is missing 0755 execute bits.",
                    "fixed": fixed,
                })

    return issues


def repair_mcp_config(
    file_path: Path,
    client_name: str,
    command: str = "uvx",
    args: Optional[List[str]] = None,
) -> Tuple[bool, Optional[Path]]:
    """Safely create a timestamped backup and repair/upsert chrome-bridge MCP config."""
    if args is None:
        args = ["--refresh", "antigravity-chrome-bridge", "mcp"]

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


def run_doctor(
    install_dir: Path,
    home_dir: Path,
    auto_fix: bool = False,
    quiet: bool = False,
) -> int:
    """Comprehensive environment health inspection and self-healing runner."""
    if not quiet:
        banner("Chrome Bridge Doctor — Diagnostics & Self-Healing")

    total_issues = 0
    total_fixed = 0

    # 1. Stale IPC Check
    with ui.spinner("Checking IPC socket and endpoint health...") as sp:
        ipc_issues = check_stale_ipc(auto_fix=auto_fix)
        if not ipc_issues:
            sp.ok("IPC socket clean (no stale or orphaned files)")
        else:
            total_issues += len(ipc_issues)
            for iss in ipc_issues:
                if iss["fixed"]:
                    total_fixed += 1
                    sp.ok(f"Repaired: {iss['title']}")
                else:
                    sp.warn(iss['title'])

    # 2. File permissions
    with ui.spinner("Verifying file permissions and launcher scripts...") as sp:
        perm_issues = check_file_permissions(install_dir, auto_fix=auto_fix)
        if not perm_issues:
            sp.ok("Host launcher permissions verified (0755)")
        else:
            total_issues += len(perm_issues)
            for iss in perm_issues:
                if iss["fixed"]:
                    total_fixed += 1
                    sp.ok(f"Repaired: {iss['title']}")
                else:
                    sp.warn(iss['title'])

    # 3. Browser Native Messaging Manifests
    with ui.spinner("Auditing browser Native Messaging Manifests...") as sp:
        manifest_targets = get_browser_manifest_targets(home_dir)
        found_count = sum(1 for _, p in manifest_targets if p.exists())
        if found_count > 0:
            sp.ok(f"Found {found_count} configured browser manifests")
        else:
            sp.warn("No browser manifests found. Run 'chrome-bridge setup' to register.")
            total_issues += 1

    # 4. MCP Configs Health
    with ui.spinner("Inspecting AI Agent MCP client configurations...") as sp:
        mcp_issues = check_mcp_configs_health(home_dir, auto_fix=auto_fix)
        if not mcp_issues:
            sp.ok("All present AI agent MCP configs are healthy")
        else:
            total_issues += len(mcp_issues)
            for iss in mcp_issues:
                if iss["fixed"]:
                    total_fixed += 1
                    sp.ok(f"Repaired: {iss['title']}")
                else:
                    sp.warn(iss['title'])

    if not quiet:
        print()
        if total_issues == 0:
            print(ui.card("Doctor Summary: All Systems Operational", [
                ("Health Status", ui.green("100% HEALTHY")),
                ("Self-Healing", "No repairs needed"),
            ]))
        else:
            status_text = ui.green(f"{total_fixed}/{total_issues} ISSUES REPAIRED") if auto_fix else ui.yellow(f"{total_issues} ISSUES DETECTED")
            print(ui.card("Doctor Summary", [
                ("Status", status_text),
                ("Next Action", "All issues resolved" if total_fixed == total_issues else f"Run with {ui.cyan('--fix')} to auto-repair"),
            ]))

    return 0 if (total_issues == 0 or total_fixed == total_issues) else 1


def run_status(args: argparse.Namespace) -> int:
    """Print system diagnostics and configuration health."""
    home_dir = resolve_home_dir()
    install_dir = resolve_install_dir(args.target, bool(getattr(args, "dev", False)))

    banner("Chrome Bridge — Diagnostics & Status")

    venv_dir = install_dir / ".venv"
    venv_py = venv_dir / ("Scripts/python.exe" if IS_WINDOWS else "bin/python3")
    has_venv = venv_py.exists()

    host_script = install_dir / "native_host.py"
    host_wrapper = install_dir / ("native-host.bat" if IS_WINDOWS else "native-host.sh")
    mcp_server = install_dir / "mcp_server.py"
    agent_skill = home_dir / ".agent" / "skills" / "chrome-bridge" / "SKILL.md"
    ext_dir = resolve_extension_dir(install_dir)

    print(ui.card("System & Runtime Diagnostics", [
        ("Platform", f"{platform.system()} ({platform.machine()}) - {platform.release()}"),
        ("Python", f"{sys.version.split()[0]} ({sys.executable})"),
        ("Runtime Root", f"{install_dir} ({'Found' if install_dir.exists() else 'Missing'})"),
        ("Extension Dir", f"{ext_dir} ({'Found' if ext_dir.exists() else 'Missing'})"),
        ("Python venv", f"{venv_py} ({'Active' if has_venv else 'Not Provisioned'})"),
        ("Native Host", f"{host_script} ({'Present' if host_script.exists() else 'Missing'})"),
        ("Host Launcher", f"{host_wrapper} ({'Present' if host_wrapper.exists() else 'Not Generated'})"),
        ("MCP Server", f"{mcp_server} ({'Present' if mcp_server.exists() else 'Missing'})"),
        ("Agent Skill", f"{agent_skill} ({'Installed' if agent_skill.exists() else 'Not Installed'})"),
    ]))
    print()

    browsers = detect_installed_browsers(home_dir)
    browser_items = []
    for b in browsers:
        status_parts = []
        if b.is_running:
            status_parts.append(ui.green("Running"))
        if b.manifest_path.exists():
            status_parts.append(ui.green("Manifest Configured"))
        else:
            status_parts.append(ui.yellow("No Manifest"))
        browser_items.append((b.name, f"[{' | '.join(status_parts)}] ({b.manifest_path})"))

    if browser_items:
        print(ui.card("Browser Native Messaging Manifests", browser_items))
    else:
        print(ui.yellow("⚠️ No browsers detected in default paths."))
    print()

    clients = detect_mcp_clients(home_dir)
    client_items = []
    for c in clients:
        if c.is_present:
            st = ui.green("Configured") if c.is_configured else ui.yellow("Missing entry")
            client_items.append((c.name, f"[{st}] {c.config_path}"))
        else:
            client_items.append((c.name, ui.dim(f"Not present ({c.config_path})")))

    print(ui.card("AI Agent MCP Configurations", client_items))
    print()
    return 0


def run_cleanup(args: argparse.Namespace) -> int:
    """Remove registered manifests, launcher scripts, and IPC endpoint files."""
    home_dir = resolve_home_dir()
    install_dir = resolve_install_dir(args.target, bool(getattr(args, "dev", False)))

    print(bold("Cleaning up Chrome Bridge native manifests, launchers, and endpoints..."))
    targets = get_browser_manifest_targets(home_dir)
    for _, path in targets:
        if path.exists():
            try:
                path.unlink()
                print(f"  {green('✓')} Removed {path}")
            except Exception:
                pass

    for fname in ("native-host.sh", "native-host.bat", f"{HOST_NAME}.json"):
        p = install_dir / fname
        if p.exists():
            try:
                p.unlink()
                print(f"  {green('✓')} Removed {p}")
            except Exception:
                pass

    import tempfile
    for temp_name in ("antigravity_chrome_bridge.sock", "antigravity_chrome_bridge.port"):
        t_path = Path(tempfile.gettempdir()) / temp_name
        if t_path.exists():
            try:
                t_path.unlink()
                print(f"  {green('✓')} Unlinked IPC endpoint: {t_path}")
            except Exception:
                pass

    if IS_WINDOWS:
        reg_subkeys = [
            rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}",
            rf"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\{HOST_NAME}",
            rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST_NAME}",
            rf"Software\Chromium\NativeMessagingHosts\{HOST_NAME}",
        ]
        try:
            import winreg
            for subkey in reg_subkeys:
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)
                    print(f"  {green('✓')} Deleted Windows Registry Key: {dim(subkey)}")
                except Exception:
                    pass
        except Exception:
            for subkey in reg_subkeys:
                try:
                    subprocess.run(
                        ["reg.exe", "delete", f"HKCU\\{subkey}", "/f"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                except Exception:
                    pass

    print(green("Cleanup complete."))
    return 0


def run_test_ping(args: argparse.Namespace) -> int:
    """Verify IPC endpoint and test active connectivity."""
    print(bold("Verifying Chrome Bridge IPC connectivity..."))
    import socket
    import tempfile

    sock_path = Path(tempfile.gettempdir()) / "antigravity_chrome_bridge.sock"
    port_path = Path(tempfile.gettempdir()) / "antigravity_chrome_bridge.port"

    if IS_WINDOWS:
        if not port_path.exists():
            print(f"  {yellow('○')} Native host port file not active (host is idle until Chrome opens).")
            return 0
        try:
            port = int(port_path.read_text(encoding="utf-8").strip())
            with socket.create_connection(("127.0.0.1", port), timeout=2.0) as s:
                s.settimeout(2.0)
                s.sendall(b'{"id":9999,"action":"ping"}\n')
                print(f"  {green('✓')} Successfully connected to Native Host TCP port {port}.")
                return 0
        except Exception as e:
            print(f"  {yellow('⚠️')} Host port file present but connection failed: {e}")
            return 1
    else:
        if not sock_path.exists():
            print(f"  {yellow('○')} Native host socket not active (host is idle until Chrome opens).")
            return 0
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect(str(sock_path))
                s.sendall(b'{"id":9999,"action":"ping"}\n')
                print(f"  {green('✓')} Successfully connected and verified Native Host Unix socket: {sock_path}")
                return 0
        except Exception as e:
            print(f"  {yellow('⚠️')} Host socket file present but connection failed: {e}")
            return 1


def main() -> None:
    """Main CLI entrypoint."""
    raw_args = sys.argv[1:]

    if raw_args and raw_args[0] == "mcp":
        import mcp_server
        mcp_server.main()
        return
    elif raw_args and raw_args[0] == "native-host":
        import native_host
        native_host.main()
        return

    parser = argparse.ArgumentParser(
        prog="chrome-bridge",
        description="Chrome Bridge — Pure Python Live Setup & Manifest Registrar",
    )
    parser.add_argument("command", nargs="?", default="setup", choices=["setup", "doctor", "status", "cleanup", "uninstall", "test", "simulate", "help"], help="Subcommand to execute (default: setup)")
    parser.add_argument("--dev", "--local", action="store_true", dest="dev", help="Configure host pointing directly to current directory")
    parser.add_argument("--target", type=str, help="Specify custom installation root directory")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive wizard")
    parser.add_argument("--no-listen", action="store_true", help="Skip waiting for live extension handshake")
    parser.add_argument("--timeout", type=float, default=15.0, help="Timeout in seconds for live handshake listener (default: 15)")
    parser.add_argument("--fix", "--repair", action="store_true", dest="fix", help="Automatically repair detected issues during doctor check")
    parser.add_argument("--simulate", action="store_true", help="Run local stdio simulator to verify host without browser")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose logging")

    parsed = parser.parse_args(raw_args)

    if parsed.command in ("help",):
        parser.print_help()
        sys.exit(0)
    elif parsed.command == "simulate" or parsed.simulate:
        install_dir = resolve_install_dir(parsed.target, bool(getattr(parsed, "dev", False)))
        python_exec = resolve_python_executable(install_dir)
        host_script = install_dir / "native_host.py"
        if not host_script.exists():
            host_script = Path(__file__).resolve().parent / "native_host.py"
        ok, msg, lat = simulate_native_host(python_exec, host_script)
        if ok:
            print(f"{green('✓')} {msg}")
            sys.exit(0)
        else:
            print(f"{red('✗')} {msg}")
            sys.exit(1)
    elif parsed.command == "doctor":
        home_dir = resolve_home_dir()
        install_dir = resolve_install_dir(parsed.target, bool(getattr(parsed, "dev", False)))
        sys.exit(run_doctor(install_dir=install_dir, home_dir=home_dir, auto_fix=bool(parsed.fix), quiet=parsed.quiet))
    elif parsed.command == "status":
        sys.exit(run_status(parsed))
    elif parsed.command in ("cleanup", "uninstall"):
        sys.exit(run_cleanup(parsed))
    elif parsed.command == "test":
        sys.exit(run_test_ping(parsed))
    else:
        sys.exit(run_setup(parsed))


if __name__ == "__main__":
    main()
