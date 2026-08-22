#!/usr/bin/env python3
"""Chrome Bridge - Pure Python Host Registration & Setup CLI.

Standard library only. Manages cross-platform native messaging manifest registration,
launcher wrapper scripts, agent skill deployment, and MCP client configurations
(Claude Code, Antigravity, Cursor, Claude Desktop, Codex, Pi Code).
"""

import argparse
import os
import platform
import sys
import tempfile
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from chrome_bridge.ui import (
    SpinnerContext,
    TerminalUI,
    badge_done,
    badge_fail,
    badge_warn,
    banner,
    blue,
    bold,
    card,
    colorize,
    cyan,
    dim,
    green,
    magenta,
    red,
    spinner,
    ui,
    yellow,
)

from chrome_bridge.manifests import (
    EXTENSION_ID,
    HOST_NAME,
    IS_LINUX,
    IS_MAC,
    IS_WINDOWS,
    PROCDIR_OVERRIDE,
    BrowserInfo,
    detect_installed_browsers,
    detect_running_browsers,
    generate_host_launcher,
    get_browser_manifest_targets,
    install_agent_skill,
    register_browser_manifests,
    resolve_extension_dir,
    resolve_home_dir,
    resolve_install_dir,
    resolve_python_executable,
    sync_runtime_files,
)

from chrome_bridge.mcp_config import (
    MCPClientInfo,
    check_mcp_configs_health,
    configure_all_mcp_clients,
    detect_mcp_clients,
    repair_mcp_config,
    update_mcp_client_config,
)

from chrome_bridge.doctor import (
    check_file_permissions,
    check_stale_ipc,
    simulate_native_host,
    wait_for_extension_handshake,
    DoctorEngine,
)

from chrome_bridge.provisioner import (
    HealthReport,
    ProvisionOptions,
    ProvisionReport,
    SystemProvisioner,
)


def run_setup(args: argparse.Namespace) -> int:
    """Execute standard setup workflow with live terminal UI and discovery prober."""
    source_dir = Path(__file__).resolve().parent
    home_dir = resolve_home_dir()
    install_dir = resolve_install_dir(args.target, bool(getattr(args, "dev", False)))
    quiet = args.quiet
    is_dev = bool(getattr(args, "dev", False))

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
        skill_src = install_agent_skill(install_dir, source_dir, home_dir, quiet=True)
        if skill_src:
            sp.ok(f"Agent skill deployed to agent directories (source: {skill_src})")
        else:
            sp.warn("Agent skill source file (SKILL.md) not found across candidate paths")

    # Step 5: Configure MCP Clients
    with ui.spinner("Configuring AI Agent Model Context Protocol (MCP) clients...") as sp:
        configure_all_mcp_clients(install_dir, home_dir, python_exec, is_dev=is_dev, quiet=True)
        clients = detect_mcp_clients(home_dir)
        configured_clients = [c.name for c in clients if c.is_configured]
        sp.ok(f"Configured {len(configured_clients)} MCP client(s): {', '.join(configured_clients)}")

    ext_dir = resolve_extension_dir(install_dir, source_dir)

    if not quiet:
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

    # Live Handshake Verification Loop
    if not quiet and not getattr(args, "no_listen", False):
        print(bold("📡 LIVE EXTENSION VERIFICATION:"))
        timeout = float(getattr(args, "timeout", 15.0) or 15.0)
        wait_for_extension_handshake(timeout_sec=timeout)

    return 0


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


def run_doctor(
    install_dir: Path,
    home_dir: Path,
    auto_fix: bool = False,
    quiet: bool = False,
) -> int:
    """Comprehensive environment health inspection and self-healing runner."""
    if not quiet:
        banner("Chrome Bridge Doctor — Diagnostics & Self-Healing")

    engine = DoctorEngine(install_dir=install_dir, home_dir=home_dir)
    
    with ui.spinner("Running diagnostic probes...") as sp:
        total_issues_count, total_fixed, issues = engine.diagnose(auto_fix=auto_fix)
        if total_issues_count == 0:
            sp.ok("All systems clean")
        else:
            for iss in issues:
                if iss.fixed:
                    sp.ok(f"Repaired: {iss.title}")
                else:
                    sp.warn(iss.title)

    if not quiet:
        print()
        if total_issues_count == 0:
            print(ui.card("Doctor Summary: All Systems Operational", [
                ("Health Status", ui.green("100% HEALTHY")),
                ("Self-Healing", "No repairs needed"),
            ]))
        else:
            status_text = ui.green(f"{total_fixed}/{total_issues_count} ISSUES REPAIRED") if auto_fix else ui.yellow(f"{total_issues_count} ISSUES DETECTED")
            print(ui.card("Doctor Summary", [
                ("Status", status_text),
                ("Next Action", "All issues resolved" if total_fixed == total_issues_count else f"Run with {ui.cyan('--fix')} to auto-repair"),
            ]))

    return 0 if (total_issues_count == 0 or total_fixed == total_issues_count) else 1


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



if __name__ == '__main__':
    main()
