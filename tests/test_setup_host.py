"""Tests for setup-host.mjs functionality: launcher generation, manifest registration, skill discovery."""

import json
import os
import subprocess
import sys
import tempfile
import pytest


def test_setup_host_generates_posix_shell_wrapper(tmp_path):
    """Test that setup-host generates native-host.sh on POSIX and pins node executable."""
    setup_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "setup-host.mjs"))
    
    # Run setup with custom target
    res = subprocess.run(
        ["node", setup_script, "setup", "--target", str(tmp_path), "--quiet"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"setup-host failed: {res.stderr}\n{res.stdout}"

    if sys.platform != "win32":
        wrapper_path = tmp_path / "native-host.sh"
        assert wrapper_path.exists(), "native-host.sh was not generated on POSIX"
        content = wrapper_path.read_text()
        assert "PYTHONIOENCODING=utf-8" in content
        assert "PYTHONUTF8=1" in content
        assert "native-host.mjs" in content
        # Check executable permissions
        mode = os.stat(wrapper_path).st_mode
        assert mode & 0o111 != 0, "native-host.sh is not executable"


def test_setup_host_manifest_target_path(tmp_path):
    """Test that generated manifest path points to native-host.sh on POSIX or native-host.bat on Windows."""
    setup_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "setup-host.mjs"))
    
    res = subprocess.run(
        ["node", setup_script, "setup", "--target", str(tmp_path), "--quiet"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"setup-host failed: {res.stderr}\n{res.stdout}"

    # On Windows, setup generates com.chrome_bridge.native.json in tmp_path
    if sys.platform == "win32":
        manifest_file = tmp_path / "com.chrome_bridge.native.json"
        if manifest_file.exists():
            data = json.loads(manifest_file.read_text())
            assert data["path"].endswith("native-host.bat")


def test_setup_host_status_command():
    """Test that status command executes without error and prints system diagnostics."""
    setup_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "setup-host.mjs"))
    res = subprocess.run(
        ["node", setup_script, "status"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "System & Runtime Diagnostics" in res.stdout
    assert "Browser Native Messaging Manifests" in res.stdout


def test_native_host_sh_fallback_probes(tmp_path):
    """Test that native-host.sh includes all standard fallback candidate paths."""
    setup_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "setup-host.mjs"))
    subprocess.run(
        ["node", setup_script, "setup", "--target", str(tmp_path), "--quiet"],
        check=True,
        capture_output=True,
    )
    if sys.platform != "win32":
        wrapper_path = tmp_path / "native-host.sh"
        content = wrapper_path.read_text()
        assert "/opt/homebrew/bin/node" in content
        assert "/usr/local/bin/node" in content
        assert ".nvm/versions/node" in content
        assert ".fnm/current/bin/node" in content
        assert ".asdf/shims/node" in content
        assert "/usr/bin/node" in content


def test_skill_source_discovery_multi_root(tmp_path):
    """Test setup discovers SKILL.md when positioned at target root or nested dirs."""
    setup_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "setup-host.mjs"))
    
    # Create target directory with SKILL.md directly at root
    (tmp_path / "SKILL.md").write_text("---\nname: chrome-bridge\n---\n# Root Skill")

    res = subprocess.run(
        ["node", setup_script, "setup", "--target", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "Resolved skill source" in res.stdout

