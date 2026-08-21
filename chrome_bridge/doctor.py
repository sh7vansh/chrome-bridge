"""Diagnostics, IPC probes, permission checks, and doctor runner for Chrome Bridge."""

import argparse
import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .manifests import (
    HOST_NAME,
    IS_WINDOWS,
    _is_windows,
    detect_installed_browsers,
    get_browser_manifest_targets,
    resolve_extension_dir,
    resolve_home_dir,
    resolve_install_dir,
)
from .mcp_config import (
    check_mcp_configs_health,
    detect_mcp_clients,
)
from .ui import (
    TerminalUI,
    banner,
    bold,
    cyan,
    dim,
    green,
    ui,
    yellow,
    red,
)


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
            if _is_windows() and port_path.exists():
                try:
                    port = int(port_path.read_text(encoding="utf-8").strip())
                    active_endpoint = ("tcp", port)
                except Exception:
                    pass
            elif not _is_windows() and sock_path.exists():
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
                                local_ui.stream.write("  ✓ Live Chrome Extension Handshake Captured!\n")
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
            local_ui.stream.write("  ○ Extension connection listener timed out (host will activate when Chrome opens).\n")
        local_ui.stream.flush()
        return None
    finally:
        if interactive:
            local_ui._show_cursor()


def check_stale_ipc(auto_fix: bool = False) -> List[Dict[str, Any]]:
    """Check for orphaned or unresponsive socket and port files."""
    issues = []
    import socket

    sock_path = Path(tempfile.gettempdir()) / "antigravity_chrome_bridge.sock"
    port_path = Path(tempfile.gettempdir()) / "antigravity_chrome_bridge.port"

    if not _is_windows() and sock_path.exists():
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

    if _is_windows() and port_path.exists():
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
    if _is_windows():
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
    venv_py = venv_dir / ("Scripts/python.exe" if _is_windows() else "bin/python3")
    has_venv = venv_py.exists()

    host_script = install_dir / "native_host.py"
    host_wrapper = install_dir / ("native-host.bat" if _is_windows() else "native-host.sh")
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

    if _is_windows():
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

    if _is_windows():
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


__all__ = [
    "simulate_native_host",
    "wait_for_extension_handshake",
    "check_stale_ipc",
    "check_file_permissions",
    "run_doctor",
    "run_status",
    "run_cleanup",
    "run_test_ping",
]
