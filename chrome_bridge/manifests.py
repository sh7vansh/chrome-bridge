"""Browser discovery, Native Messaging Host manifest registration, and launcher wrappers."""

import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .ui import bold, cyan, dim, green, ui, yellow

HOST_NAME = "com.chrome_bridge.native"
EXTENSION_ID = "nbghhppoiigjbdjbhefiaijofpnhgepb"
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

PROCDIR_OVERRIDE: Optional[Path] = None


def _is_windows() -> bool:
    sh = sys.modules.get("setup_host")
    if sh and hasattr(sh, "IS_WINDOWS"):
        return bool(getattr(sh, "IS_WINDOWS"))
    return IS_WINDOWS


def _is_mac() -> bool:
    sh = sys.modules.get("setup_host")
    if sh and hasattr(sh, "IS_MAC"):
        return bool(getattr(sh, "IS_MAC"))
    return IS_MAC


def _is_linux() -> bool:
    sh = sys.modules.get("setup_host")
    if sh and hasattr(sh, "IS_LINUX"):
        return bool(getattr(sh, "IS_LINUX"))
    return IS_LINUX


def _procdir_override() -> Optional[Path]:
    sh = sys.modules.get("setup_host")
    if sh and hasattr(sh, "PROCDIR_OVERRIDE"):
        val = getattr(sh, "PROCDIR_OVERRIDE")
        if val is not None:
            return val
    return PROCDIR_OVERRIDE


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


def resolve_home_dir() -> Path:
    """Resolve user home directory respecting HOME / USERPROFILE env overrides."""
    sh = sys.modules.get("setup_host")
    if sh and hasattr(sh, "resolve_home_dir") and sh.resolve_home_dir != resolve_home_dir:
        return sh.resolve_home_dir()
    if "HOME" in os.environ:
        return Path(os.environ["HOME"])
    if "USERPROFILE" in os.environ:
        return Path(os.environ["USERPROFILE"])
    return Path.home()


def resolve_install_dir(target_arg: Optional[str] = None, is_dev: bool = False) -> Path:
    """Determine installation root directory."""
    sh = sys.modules.get("setup_host")
    if sh and hasattr(sh, "resolve_install_dir") and sh.resolve_install_dir != resolve_install_dir:
        return sh.resolve_install_dir(target_arg, is_dev)
    if target_arg:
        return Path(target_arg).resolve()
    if is_dev:
        return Path(__file__).resolve().parent.parent
    return resolve_home_dir() / ".chrome-bridge"


def resolve_extension_dir(install_dir: Path, source_dir: Optional[Path] = None) -> Path:
    """Resolve the unpacked Chrome extension directory path."""
    inst_ext = install_dir / "extension"
    if inst_ext.exists():
        return inst_ext.resolve()

    src = source_dir or Path(__file__).resolve().parent.parent
    src_ext = src / "extension"
    if src_ext.exists():
        return src_ext.resolve()

    return inst_ext.resolve()


def resolve_python_executable(install_dir: Path) -> str:
    """Find the most appropriate Python executable."""
    venv_dir = install_dir / ".venv"
    if _is_windows():
        venv_py = venv_dir / "Scripts" / "python.exe"
    else:
        venv_py = venv_dir / "bin" / "python3"

    if venv_py.exists():
        return str(venv_py)

    if sys.version_info >= (3, 10):
        return sys.executable

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

    for dname in (".agents", "chrome_bridge", "extension", "skills"):
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

    if _is_windows():
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
        sh_path.chmod(sh_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        if (install_dir / "native_host.py").exists():
            nh_py = install_dir / "native_host.py"
            nh_py.chmod(nh_py.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        if not quiet:
            print(f"  {green('✓')} Generated POSIX Host Shell Wrapper (0755): {sh_path}")
        return sh_path


def detect_running_browsers() -> List[str]:
    """Detect currently running Chromium-based browser processes."""
    running: List[str] = []

    if _is_linux():
        proc_dir = _procdir_override() or Path("/proc")
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
    elif _is_mac():
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
    elif _is_windows():
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

    if _is_linux():
        targets.extend([
            ("Google Chrome", home_dir / ".config" / "google-chrome" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Chromium", home_dir / ".config" / "chromium" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Brave Browser", home_dir / ".config" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Microsoft Edge", home_dir / ".config" / "microsoft-edge" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Vivaldi", home_dir / ".config" / "vivaldi" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Arc", home_dir / ".config" / "arc" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Google Chrome (Flatpak)", home_dir / ".var" / "app" / "com.google.Chrome" / "config" / "google-chrome" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Chromium (Flatpak)", home_dir / ".var" / "app" / "org.chromium.Chromium" / "config" / "chromium" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Brave Browser (Flatpak)", home_dir / ".var" / "app" / "com.brave.Browser" / "config" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Microsoft Edge (Flatpak)", home_dir / ".var" / "app" / "com.microsoft.Edge" / "config" / "microsoft-edge" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Chromium (Snap)", home_dir / "snap" / "chromium" / "current" / ".config" / "chromium" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Brave Browser (Snap)", home_dir / "snap" / "brave" / "current" / ".config" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
            ("Microsoft Edge (Snap)", home_dir / "snap" / "edge" / "current" / ".config" / "microsoft-edge" / "NativeMessagingHosts" / f"{HOST_NAME}.json"),
        ])
    elif _is_mac():
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
        elif _is_windows():
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

    if _is_windows():
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


def install_agent_skill(install_dir: Path, source_dir: Path, home_dir: Path, quiet: bool = False) -> Optional[Path]:
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
        return None

    if not quiet:
        print(f"  {cyan('↳ Resolved skill source:')} {skill_source}")

    dest_dirs = [
        ("Antigravity Global Agent (.agents)", home_dir / ".agents" / "skills" / "chrome-bridge"),
        ("Antigravity Global Agent (.agent)", home_dir / ".agent" / "skills" / "chrome-bridge"),
        ("Gemini CLI Agent", home_dir / ".gemini" / "antigravity-cli" / "skills" / "chrome-bridge"),
        ("Gemini Config Skills", home_dir / ".gemini" / "config" / "skills" / "chrome-bridge"),
        ("Codex Global Skill", home_dir / ".codex" / "skills" / "chrome-bridge"),
        ("Pi Code Global Skill", home_dir / ".pi" / "skills" / "chrome-bridge"),
        ("Pi Agent Global Skill", home_dir / ".pi" / "agent" / "skills" / "chrome-bridge"),
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

    return skill_source


__all__ = [
    "HOST_NAME",
    "EXTENSION_ID",
    "IS_WINDOWS",
    "IS_MAC",
    "IS_LINUX",
    "PROCDIR_OVERRIDE",
    "BrowserInfo",
    "resolve_home_dir",
    "resolve_install_dir",
    "resolve_extension_dir",
    "resolve_python_executable",
    "sync_runtime_files",
    "generate_host_launcher",
    "detect_running_browsers",
    "get_browser_manifest_targets",
    "detect_installed_browsers",
    "register_browser_manifests",
    "install_agent_skill",
]
