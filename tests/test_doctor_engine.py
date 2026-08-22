"""Unit tests for chrome_bridge.doctor subsystem."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from chrome_bridge.doctor import (
    check_stale_ipc,
    check_file_permissions,
)


def test_check_stale_ipc_posix_no_socket(tmp_path):
    with patch("chrome_bridge.doctor._is_windows", return_value=False), \
         patch("tempfile.gettempdir", return_value=str(tmp_path)):
        issues = check_stale_ipc(auto_fix=False)
        assert len(issues) == 0


def test_check_stale_ipc_detects_unresponsive_socket(tmp_path):
    dead_sock = tmp_path / "antigravity_chrome_bridge.sock"
    dead_sock.touch()

    with patch("chrome_bridge.doctor._is_windows", return_value=False), \
         patch("tempfile.gettempdir", return_value=str(tmp_path)):
        issues = check_stale_ipc(auto_fix=True)
        assert len(issues) == 1
        assert issues[0]["fixed"] is True
        assert not dead_sock.exists()


def test_doctor_engine_pluggable_probes(tmp_path):
    from chrome_bridge.doctor import DoctorEngine, DiagnosticProbe, DiagnosticIssue

    engine = DoctorEngine(install_dir=tmp_path, home_dir=tmp_path)
    assert len(engine.probes) >= 4

    class CustomTestProbe:
        name = "Custom Check"
        category = "Custom"
        def check(self, install_dir: Path, home_dir: Path, auto_fix: bool = False):
            return [DiagnosticIssue(type="custom", title="Test Issue", detail="Testing", fixed=auto_fix)]

    custom_probe = CustomTestProbe()
    assert isinstance(custom_probe, DiagnosticProbe)

    engine.register_probe(custom_probe)
    total, fixed, issues = engine.diagnose(auto_fix=False)
    assert total >= 1
    assert any(i.type == "custom" for i in issues)

    total_repaired, fixed_repaired, issues_repaired = engine.diagnose(auto_fix=True)
    assert any(i.type == "custom" and i.fixed for i in issues_repaired)

