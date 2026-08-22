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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union, runtime_checkable

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


@dataclass
class DiagnosticIssue:
    """Represents an issue discovered during environment diagnostics."""
    type: str
    title: str
    detail: str
    fixed: bool = False
    severity: str = "warning"


@runtime_checkable
class DiagnosticProbe(Protocol):
    """Protocol seam for environment diagnostic checks and self-healing remediators."""
    name: str
    category: str

    def check(self, install_dir: Path, home_dir: Path, auto_fix: bool = False) -> List[DiagnosticIssue]:
        """Perform diagnostic audit and optional remediation."""
        ...


class IpcEndpointProbe:
    """Audits and remediates orphaned or stale socket and port files."""
    name = "IPC Endpoint Health"
    category = "Transport"

    def check(self, install_dir: Path, home_dir: Path, auto_fix: bool = False) -> List[DiagnosticIssue]:
        raw_issues = check_stale_ipc(auto_fix=auto_fix)
        return [
            DiagnosticIssue(
                type=i.get("type", "stale_ipc"),
                title=i.get("title", "Stale IPC endpoint"),
                detail=i.get("detail", ""),
                fixed=i.get("fixed", False),
                severity="warning",
            )
            for i in raw_issues
        ]


class FilePermissionProbe:
    """Audits and remediates POSIX launcher executable permissions."""
    name = "Launcher Script Permissions"
    category = "System"

    def check(self, install_dir: Path, home_dir: Path, auto_fix: bool = False) -> List[DiagnosticIssue]:
        raw_issues = check_file_permissions(install_dir, auto_fix=auto_fix)
        return [
            DiagnosticIssue(
                type=i.get("type", "permission"),
                title=i.get("title", "Missing executable permissions"),
                detail=i.get("detail", ""),
                fixed=i.get("fixed", False),
                severity="warning",
            )
            for i in raw_issues
        ]


class BrowserManifestProbe:
    """Audits browser Native Messaging host manifests."""
    name = "Browser Native Manifests"
    category = "Registration"

    def check(self, install_dir: Path, home_dir: Path, auto_fix: bool = False) -> List[DiagnosticIssue]:
        manifest_targets = get_browser_manifest_targets(home_dir)
        found_count = sum(1 for _, p in manifest_targets if p.exists())
        if found_count == 0:
            return [
                DiagnosticIssue(
                    type="manifest",
                    title="No browser Native Messaging manifests found",
                    detail="Run 'chrome-bridge setup' to register manifests for installed browsers.",
                    fixed=False,
                    severity="warning",
                )
            ]
        return []


class McpConfigProbe:
    """Audits and remediates AI agent MCP client configurations."""
    name = "AI Agent MCP Configs"
    category = "Client"

    def check(self, install_dir: Path, home_dir: Path, auto_fix: bool = False) -> List[DiagnosticIssue]:
        raw_issues = check_mcp_configs_health(home_dir, auto_fix=auto_fix)
        return [
            DiagnosticIssue(
                type=i.get("type", "mcp_config"),
                title=i.get("title", "MCP configuration issue"),
                detail=i.get("detail", ""),
                fixed=i.get("fixed", False),
                severity="warning",
            )
            for i in raw_issues
        ]


class DoctorEngine:
    """Pluggable diagnostic engine coordinating environment audits and self-healing."""

    def __init__(self, install_dir: Optional[Path] = None, home_dir: Optional[Path] = None):
        self.install_dir = install_dir or resolve_install_dir(None)
        self.home_dir = home_dir or resolve_home_dir()
        self.probes: List[DiagnosticProbe] = [
            IpcEndpointProbe(),
            FilePermissionProbe(),
            BrowserManifestProbe(),
            McpConfigProbe(),
        ]

    def register_probe(self, probe: DiagnosticProbe) -> None:
        """Register a custom diagnostic probe."""
        self.probes.append(probe)

    def diagnose(self, auto_fix: bool = False) -> Tuple[int, int, List[DiagnosticIssue]]:
        """Run all registered diagnostic probes and return summary (total_issues, total_fixed, issues)."""
        all_issues: List[DiagnosticIssue] = []
        total_fixed = 0
        for probe in self.probes:
            issues = probe.check(self.install_dir, self.home_dir, auto_fix=auto_fix)
            all_issues.extend(issues)
            total_fixed += sum(1 for i in issues if i.fixed)
        return len(all_issues), total_fixed, all_issues




__all__ = [
    "simulate_native_host",
    "wait_for_extension_handshake",
    "check_stale_ipc",
    "check_file_permissions",
    "DoctorEngine",
    "DiagnosticProbe",
]
