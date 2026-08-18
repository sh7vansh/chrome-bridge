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

HOST_NAME = "com.chrome_bridge.native"
EXTENSION_ID = "nbghhppoiigjbdjbhefiaijofpnhgepb"
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# Terminal color formatting
SUPPORTS_COLOR = not os.environ.get("NO_COLOR") and (
    sys.stdout.isatty() or os.environ.get("FORCE_COLOR") == "1"
)


def _colorize(code: str, text: str) -> str:
    if not SUPPORTS_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(text: str) -> str:
    return _colorize("1", text)


def dim(text: str) -> str:
    return _colorize("2", text)


def cyan(text: str) -> str:
    return _colorize("36", text)


def green(text: str) -> str:
    return _colorize("32", text)


def yellow(text: str) -> str:
    return _colorize("33", text)


def red(text: str) -> str:
    return _colorize("31", text)


def banner() -> None:
    print(bold(cyan("================================================================")))
    print(bold(cyan("   🌐 Chrome Bridge 2.0 — Pure Python Setup & Environment       ")))
    print(bold(cyan("================================================================")))


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

        reg_keys = [
            f"HKCU\\Software\\Google\\Chrome\\NativeMessagingHosts\\{HOST_NAME}",
            f"HKCU\\Software\\BraveSoftware\\Brave-Browser\\NativeMessagingHosts\\{HOST_NAME}",
            f"HKCU\\Software\\Microsoft\\Edge\\NativeMessagingHosts\\{HOST_NAME}",
            f"HKCU\\Software\\Chromium\\NativeMessagingHosts\\{HOST_NAME}",
        ]
        for key in reg_keys:
            try:
                subprocess.run(
                    ["reg.exe", "add", key, "/ve", "/t", "REG_SZ", "/d", str(manifest_path), "/f"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if not quiet:
                    print(f"  {green('✓')} Registered Windows Registry Key: {dim(key)}")
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


def run_setup(args: argparse.Namespace) -> int:
    """Execute standard setup workflow."""
    source_dir = Path(__file__).resolve().parent
    home_dir = resolve_home_dir()
    install_dir = resolve_install_dir(args.target, bool(getattr(args, "dev", False)))
    quiet = args.quiet

    if not quiet:
        banner()
        print(f"\n{bold('📋 System Environment & Execution Context:')}")
        print(f"  • Operating System:  {platform.system()} ({platform.machine()})")
        print(f"  • Python Runtime:    {sys.version.split()[0]} ({sys.executable})")
        print(f"  • Script Source:     {source_dir}")
        print(f"  • Target Runtime:    {bold(cyan(str(install_dir)))}")
        print(f"  • Extension ID:      {bold(EXTENSION_ID)}")
        print(f"  • Native Host Name:  {bold(HOST_NAME)}\n")

    if not quiet:
        print(f"{bold(yellow('[1/5] Synchronizing Runtime Files & Assets...'))}")
    sync_runtime_files(source_dir, install_dir, quiet)

    if not quiet:
        print(f"\n{bold(yellow('[2/5] Resolving Python Runtime Environment...'))}")
    python_exec = resolve_python_executable(install_dir)
    if not quiet:
        print(f"  {green('✓')} Python environment selected: {bold(python_exec)}")

    if not quiet:
        print(f"\n{bold(yellow('[3/5] Registering Chrome Native Messaging Host...'))}")
    launcher_path = generate_host_launcher(install_dir, python_exec, quiet)
    register_browser_manifests(launcher_path, install_dir, home_dir, quiet)

    if not quiet:
        print(f"\n{bold(yellow('[4/5] Installing Agent Skill (chrome-bridge)...'))}")
    install_agent_skill(install_dir, source_dir, home_dir, quiet)

    if not quiet:
        print(f"\n{bold(yellow('[5/5] Configuring Model Context Protocol (MCP) Clients...'))}")
    is_dev = bool(getattr(args, "dev", False))
    configure_all_mcp_clients(install_dir, home_dir, python_exec, is_dev=is_dev, quiet=quiet)

    if not quiet:
        print(f"""
{bold(green("================================================================"))}
{bold(green("   🎉 Setup Complete! Chrome Bridge is Live & Ready.             "))}
{bold(green("================================================================"))}

{bold("🚀 NEXT STEPS TO CONNECT YOUR BROWSER:")}

  {bold("1. Install or Load the Chrome Extension:")}
     • Option A (Chrome Web Store):
       👉 {cyan(f"https://chromewebstore.google.com/detail/{EXTENSION_ID}")}
     • Option B (Unpacked Developer Mode):
       Open {bold("chrome://extensions/")} in Chrome, toggle {bold("Developer mode")},
       click {bold("[Load unpacked]")}, and select:
       👉 {cyan(str(install_dir / "extension"))}

  {bold("2. Verify Connection:")}
     Click the Chrome Bridge extension icon in your browser toolbar.
     It should show {green("● Connected to Native Host")}.

  {bold("3. Control Browser from your AI Assistant:")}
     Your assistant (Claude Code, Cursor, Claude Desktop, Antigravity) can now procedurally automate your browser:
     {dim('"Inspect open tabs and snapshot the active page"')}
""")
    return 0


def run_status(args: argparse.Namespace) -> int:
    """Print system diagnostics and configuration health."""
    home_dir = resolve_home_dir()
    install_dir = resolve_install_dir(args.target, bool(getattr(args, "dev", False)))

    banner()
    print(f"\n{bold('🔍 System & Runtime Diagnostics:')}\n")
    print(f"  {bold('Platform:')}       {platform.system()} ({platform.machine()}) - {platform.release()}")
    print(f"  {bold('Python:')}         {sys.version.split()[0]} ({sys.executable})")
    print(f"  {bold('Runtime Root:')}   {install_dir} {green('[Found]') if install_dir.exists() else red('[Missing]')}")

    venv_dir = install_dir / ".venv"
    venv_py = venv_dir / ("Scripts/python.exe" if IS_WINDOWS else "bin/python3")
    has_venv = venv_py.exists()
    print(f"  {bold('Python venv:')}    {venv_py} {green('[Active]') if has_venv else yellow('[Not Provisioned]')}")

    host_script = install_dir / "native_host.py"
    host_wrapper = install_dir / ("native-host.bat" if IS_WINDOWS else "native-host.sh")
    print(f"  {bold('Native Host:')}    {host_script} {green('[Present]') if host_script.exists() else red('[Missing]')}")
    print(f"  {bold('Host Launcher:')}  {host_wrapper} {green('[Present]') if host_wrapper.exists() else yellow('[Not Generated]')}")

    mcp_server = install_dir / "mcp_server.py"
    print(f"  {bold('MCP Server:')}     {mcp_server} {green('[Present]') if mcp_server.exists() else red('[Missing]')}")

    agent_skill = home_dir / ".agent" / "skills" / "chrome-bridge" / "SKILL.md"
    print(f"  {bold('Agent Skill:')}    {agent_skill} {green('[Installed]') if agent_skill.exists() else yellow('[Not Installed]')}")

    print(f"\n{bold('🌐 Browser Native Messaging Manifests:')}")
    targets = get_browser_manifest_targets(home_dir)
    if IS_WINDOWS:
        win_manifest = install_dir / f"{HOST_NAME}.json"
        targets.append(("Windows Manifest", win_manifest))

    found_manifests = 0
    for browser_name, target_file in targets:
        if target_file.exists():
            print(f"  {green('✓')} {target_file}")
            found_manifests += 1
    if found_manifests == 0:
        print(f"  {yellow('⚠️ No browser native messaging manifests found in default paths.')}")

    print(f"\n{bold('🤖 MCP Client Configurations:')}")
    mcp_clients = [
        ("Claude Code", home_dir / ".claude.json"),
        ("Antigravity Global", home_dir / ".agent" / "mcp_config.json"),
        ("Antigravity Config", home_dir / ".config" / "antigravity" / "mcp_config.json"),
        ("Antigravity CLI", home_dir / ".gemini" / "antigravity-cli" / "mcp_config.json"),
        ("Claude Desktop", home_dir / ".config" / "Claude" / "claude_desktop_config.json"),
        ("Cursor", home_dir / ".cursor" / "mcp.json"),
    ]

    for name, path in mcp_clients:
        if path.exists():
            try:
                content = json.loads(path.read_text(encoding="utf-8"))
                has_cb = isinstance(content, dict) and "mcpServers" in content and "chrome-bridge" in content["mcpServers"]
                status_str = f"{green('(Configured)')}" if has_cb else f"{yellow('(Missing chrome-bridge entry)')}"
                icon = green("✓") if has_cb else yellow("○")
                print(f"  {icon} {name}: {path} {status_str}")
            except Exception:
                print(f"  {yellow('○')} {name}: {path} {dim('(Unparseable JSON)')}")
        else:
            print(f"  {dim(f'- {name}: {path} (Not present on system)')}")

    print("\n")
    return 0


def run_cleanup(args: argparse.Namespace) -> int:
    """Remove registered manifests and launcher scripts."""
    home_dir = resolve_home_dir()
    install_dir = resolve_install_dir(args.target, bool(getattr(args, "dev", False)))

    print(bold("Cleaning up Chrome Bridge native manifests and launchers..."))
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

    print(green("Cleanup complete."))
    return 0


def run_test_ping(args: argparse.Namespace) -> int:
    """Verify IPC endpoint and basic connectivity."""
    print(bold("Verifying Chrome Bridge IPC endpoints..."))
    import tempfile
    sock_path = Path(tempfile.gettempdir()) / "antigravity_chrome_bridge.sock"
    port_path = Path(tempfile.gettempdir()) / "antigravity_chrome_bridge.port"

    if IS_WINDOWS:
        if port_path.exists():
            print(f"  {green('✓')} Port file present: {port_path} ({port_path.read_text().strip()})")
            return 0
        else:
            print(f"  {yellow('○')} Native host port file not active (host is idle until Chrome opens).")
            return 0
    else:
        if sock_path.exists():
            print(f"  {green('✓')} Unix socket active: {sock_path}")
            return 0
        else:
            print(f"  {yellow('○')} Native host socket not active (host is idle until Chrome opens).")
            return 0


def main() -> None:
    """Main CLI entrypoint."""
    # Check if first arg is a subcommand or help
    raw_args = sys.argv[1:]

    # Custom handling for mcp and native-host subcommands
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
        description="Chrome Bridge - Pure Python Setup & Manifest Registrar",
    )
    parser.add_argument("command", nargs="?", default="setup", choices=["setup", "status", "cleanup", "uninstall", "test", "help"], help="Subcommand to execute (default: setup)")
    parser.add_argument("--dev", "--local", action="store_true", dest="dev", help="Configure host pointing directly to current directory")
    parser.add_argument("--target", type=str, help="Specify custom installation root directory")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose logging")

    parsed = parser.parse_args(raw_args)

    if parsed.command in ("help",):
        parser.print_help()
        sys.exit(0)
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
