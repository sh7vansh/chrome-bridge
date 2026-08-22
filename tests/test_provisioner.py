"""Unit tests for SystemProvisioner module and high-leverage provisioning seam."""
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from chrome_bridge.doctor import DiagnosticIssue
from chrome_bridge.provisioner import (
    HealthReport,
    ProvisionOptions,
    ProvisionReport,
    SystemProvisioner,
)


def test_system_provisioner_initialization(tmp_path):
    prov = SystemProvisioner(home_dir=tmp_path)
    assert prov.home_dir == tmp_path


def test_system_provisioner_provision_workflow(tmp_path):
    prov = SystemProvisioner(home_dir=tmp_path)
    target_install = tmp_path / ".chrome-bridge"
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "SKILL.md").write_text("---\nname: chrome-bridge\n---\n# Skill\n", encoding="utf-8")

    mock_browser = MagicMock()
    mock_browser.name = "google-chrome"
    mock_browser.manifest_path = MagicMock(exists=lambda: True)

    mock_client = MagicMock()
    mock_client.name = "Claude Code"
    mock_client.is_configured = True

    with patch("chrome_bridge.provisioner.sync_runtime_files") as mock_sync, \
         patch("chrome_bridge.provisioner.resolve_python_executable", return_value="/usr/bin/python3") as mock_py, \
         patch("chrome_bridge.provisioner.generate_host_launcher", return_value=target_install / "native-host.sh") as mock_launch, \
         patch("chrome_bridge.provisioner.register_browser_manifests") as mock_reg, \
         patch("chrome_bridge.provisioner.detect_installed_browsers", return_value=[mock_browser]), \
         patch("chrome_bridge.provisioner.install_agent_skill", return_value=tmp_path / "SKILL.md"), \
         patch("chrome_bridge.provisioner.configure_all_mcp_clients"), \
         patch("chrome_bridge.provisioner.detect_mcp_clients", return_value=[mock_client]):

        opts = ProvisionOptions(
            target_dir=str(target_install),
            is_dev=False,
            source_dir=source_dir,
            home_dir=tmp_path,
            quiet=True,
        )
        report = prov.provision(opts)

        assert isinstance(report, ProvisionReport)
        assert report.success is True
        assert report.install_dir == target_install
        assert report.skill_deployed is True
        assert "google-chrome" in report.configured_browsers
        assert "Claude Code" in report.configured_mcp_clients
        mock_sync.assert_called_once()
        mock_reg.assert_called_once()


def test_system_provisioner_audit_and_repair(tmp_path):
    prov = SystemProvisioner(home_dir=tmp_path)

    with patch("chrome_bridge.provisioner.DoctorEngine") as mock_doc:
        engine_inst = mock_doc.return_value
        check_fix = DiagnosticIssue(type="manifest", title="Manifest fix", detail="Registered", fixed=True)
        engine_inst.diagnose.return_value = (1, 1, [check_fix])

        report = prov.audit_and_repair(install_dir=tmp_path / ".chrome-bridge", auto_fix=True, quiet=True)

        assert isinstance(report, HealthReport)
        assert report.passed is True
        assert report.total_issues == 1
        assert report.total_fixed == 1
        assert len(report.issues) == 1
