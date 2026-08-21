"""Unit tests for chrome_bridge.manifests subsystem."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from chrome_bridge.manifests import (
    HOST_NAME,
    EXTENSION_ID,
    BrowserInfo,
    resolve_home_dir,
    resolve_install_dir,
    resolve_extension_dir,
    resolve_python_executable,
    generate_host_launcher,
    register_browser_manifests,
    get_browser_manifest_targets,
    detect_installed_browsers,
    detect_running_browsers,
    install_agent_skill,
)


def test_manifest_targets_structure(tmp_path):
    targets = get_browser_manifest_targets(tmp_path)
    assert len(targets) > 0
    assert all(isinstance(name, str) and isinstance(p, Path) for name, p in targets)
    assert any("Google Chrome" in name for name, p in targets)


def test_generate_host_launcher_posix(tmp_path):
    with patch("chrome_bridge.manifests._is_windows", return_value=False):
        launcher = generate_host_launcher(tmp_path, "/usr/bin/python3", quiet=True)
        assert launcher.name == "native-host.sh"
        assert launcher.exists()
        content = launcher.read_text(encoding="utf-8")
        assert "PINNED_PYTHON=\"/usr/bin/python3\"" in content
        assert "native_host.py" in content


def test_register_browser_manifests_posix(tmp_path):
    home = tmp_path / "home"
    install_dir = tmp_path / "install"
    home.mkdir()
    install_dir.mkdir()
    launcher = install_dir / "native-host.sh"
    launcher.touch()

    with patch("chrome_bridge.manifests._is_windows", return_value=False):
        register_browser_manifests(launcher, install_dir, home, quiet=True)
        targets = get_browser_manifest_targets(home)
        configured = [p for _, p in targets if p.exists()]
        assert len(configured) > 0
        for p in configured:
            data = p.read_text(encoding="utf-8")
            assert HOST_NAME in data
            assert EXTENSION_ID in data
            assert str(launcher) in data


def test_install_agent_skill(tmp_path):
    install_dir = tmp_path / "install"
    source_dir = tmp_path / "source"
    home = tmp_path / "home"
    (source_dir / ".agents" / "skills" / "chrome-bridge").mkdir(parents=True)
    skill_file = source_dir / ".agents" / "skills" / "chrome-bridge" / "SKILL.md"
    skill_file.write_text("# Chrome Bridge Skill", encoding="utf-8")

    installed = install_agent_skill(install_dir, source_dir, home, quiet=True)
    assert installed is not None
    assert (home / ".agents" / "skills" / "chrome-bridge" / "SKILL.md").exists()
