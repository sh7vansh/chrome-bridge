"""Chrome Bridge - Unified System Provisioner and Environment Manager."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .doctor import DiagnosticIssue, DoctorEngine, check_file_permissions, check_stale_ipc
from .manifests import (
    EXTENSION_ID,
    HOST_NAME,
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
from .mcp_config import (
    MCPClientInfo,
    check_mcp_configs_health,
    configure_all_mcp_clients,
    detect_mcp_clients,
    repair_mcp_config,
    update_mcp_client_config,
)
from .ui import TerminalUI, ui


@dataclass
class ProvisionOptions:
    """Parameters for environment provisioning execution."""
    target_dir: Optional[str] = None
    is_dev: bool = False
    source_dir: Optional[Path] = None
    home_dir: Optional[Path] = None
    quiet: bool = False


@dataclass
class ProvisionReport:
    """Strongly-typed summary outcome of a provisioning run."""
    install_dir: Path
    extension_dir: Path
    python_exec: str
    launcher_path: Path
    configured_browsers: List[str] = field(default_factory=list)
    configured_mcp_clients: List[str] = field(default_factory=list)
    skill_deployed: bool = False
    skill_path: Optional[str] = None
    success: bool = True
    errors: List[str] = field(default_factory=list)


@dataclass
class HealthReport:
    """Aggregated results from self-healing diagnostic checks."""
    passed: bool
    issues: List[DiagnosticIssue] = field(default_factory=list)
    total_issues: int = 0
    total_fixed: int = 0


class SystemProvisioner:
    """Unified system provisioning and self-healing environment manager.

    Provides a clean 2-method interface for complete environment provisioning
    (runtime sync, host manifests, skill deployment, MCP configurations)
    and automated self-healing auditing.
    """

    def __init__(self, home_dir: Optional[Path] = None):
        self.home_dir = home_dir or resolve_home_dir()

    def provision(self, options: Optional[ProvisionOptions] = None) -> ProvisionReport:
        """Execute end-to-end environment provisioning."""
        opts = options or ProvisionOptions()
        home = opts.home_dir or self.home_dir
        source_dir = opts.source_dir or Path(__file__).resolve().parent.parent
        install_dir = resolve_install_dir(opts.target_dir, opts.is_dev)

        errors: List[str] = []

        # 1. Sync runtime files
        try:
            sync_runtime_files(source_dir, install_dir, quiet=opts.quiet)
        except Exception as e:
            errors.append(f"Runtime sync failed: {e}")

        # 2. Resolve Python
        python_exec = resolve_python_executable(install_dir)

        # 3. Generate launcher & register manifests
        launcher_path = generate_host_launcher(install_dir, python_exec, quiet=opts.quiet)
        register_browser_manifests(launcher_path, install_dir, home, quiet=opts.quiet)
        browsers = detect_installed_browsers(home)
        configured_browsers = [b.name for b in browsers if b.manifest_path.exists()]

        # 4. Install Agent Skill
        skill_src = install_agent_skill(install_dir, source_dir, home, quiet=opts.quiet)

        # 5. Configure MCP Clients
        configure_all_mcp_clients(install_dir, home, python_exec, is_dev=opts.is_dev, quiet=opts.quiet)
        clients = detect_mcp_clients(home)
        configured_clients = [c.name for c in clients if c.is_configured]

        ext_dir = resolve_extension_dir(install_dir, source_dir)

        return ProvisionReport(
            install_dir=install_dir,
            extension_dir=ext_dir,
            python_exec=python_exec,
            launcher_path=launcher_path,
            configured_browsers=configured_browsers,
            configured_mcp_clients=configured_clients,
            skill_deployed=bool(skill_src),
            skill_path=str(skill_src) if skill_src else None,
            success=len(errors) == 0,
            errors=errors,
        )

    def audit_and_repair(
        self,
        install_dir: Optional[Path] = None,
        auto_fix: bool = False,
        quiet: bool = False,
    ) -> HealthReport:
        """Run system health audit across manifests, runtime, and MCP configurations with optional repair."""
        target_install = install_dir or resolve_install_dir()
        engine = DoctorEngine(install_dir=target_install, home_dir=self.home_dir)
        total_issues, total_fixed, issues = engine.diagnose(auto_fix=auto_fix)
        passed = (total_issues - total_fixed) == 0
        return HealthReport(
            passed=passed,
            issues=issues,
            total_issues=total_issues,
            total_fixed=total_fixed,
        )
