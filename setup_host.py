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
    run_cleanup,
    run_doctor,
    run_status,
    run_test_ping,
    simulate_native_host,
    wait_for_extension_handshake,
)


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
        skill_src = install_agent_skill(install_dir, source_dir, home_dir, quiet=True)
        if skill_src:
            sp.ok(f"Agent skill deployed to agent directories (source: {skill_src})")
        else:
            sp.warn("Agent skill source file (SKILL.md) not found across candidate paths")

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
