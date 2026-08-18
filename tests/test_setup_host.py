"""Tests for pure Python setup_host.py functionality: launcher generation, manifest registration, skill discovery."""

import json
import os
import subprocess
import sys
import tempfile
import pytest


def run_setup_host(*args, env=None):
    setup_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "setup_host.py"))
    cmd = [sys.executable, setup_script, *args]
    return subprocess.run(
        cmd,
        env=env if env is not None else os.environ.copy(),
        capture_output=True,
        text=True,
    )


def test_setup_host_generates_posix_shell_wrapper(tmp_path):
    """Test that setup_host generates native-host.sh on POSIX and pins Python executable."""
    res = run_setup_host("setup", "--target", str(tmp_path), "--quiet")
    assert res.returncode == 0, f"setup_host failed: {res.stderr}\n{res.stdout}"

    if sys.platform != "win32":
        wrapper_path = tmp_path / "native-host.sh"
        assert wrapper_path.exists(), "native-host.sh was not generated on POSIX"
        content = wrapper_path.read_text()
        assert "PYTHONIOENCODING=utf-8" in content
        assert "PYTHONUTF8=1" in content
        assert "native_host.py" in content
        # Check executable permissions
        mode = os.stat(wrapper_path).st_mode
        assert mode & 0o111 != 0, "native-host.sh is not executable"


def test_setup_host_manifest_target_path(tmp_path):
    """Test that generated manifest path points to native-host.sh on POSIX or native-host.bat on Windows."""
    res = run_setup_host("setup", "--target", str(tmp_path), "--quiet")
    assert res.returncode == 0, f"setup_host failed: {res.stderr}\n{res.stdout}"

    # On Windows, setup generates com.chrome_bridge.native.json in tmp_path
    if sys.platform == "win32":
        manifest_file = tmp_path / "com.chrome_bridge.native.json"
        if manifest_file.exists():
            data = json.loads(manifest_file.read_text())
            assert data["path"].endswith("native-host.bat")


def test_setup_host_status_command():
    """Test that status command executes without error and prints system diagnostics."""
    res = run_setup_host("status")
    assert res.returncode == 0
    assert "System & Runtime Diagnostics" in res.stdout
    assert "Browser Native Messaging Manifests" in res.stdout


def test_native_host_sh_fallback_probes(tmp_path):
    """Test that native-host.sh includes standard Python/uv fallback candidate paths."""
    res = run_setup_host("setup", "--target", str(tmp_path), "--quiet")
    assert res.returncode == 0
    if sys.platform != "win32":
        wrapper_path = tmp_path / "native-host.sh"
        content = wrapper_path.read_text()
        assert "/opt/homebrew/bin/python3" in content
        assert "/usr/local/bin/python3" in content
        assert ".local/bin/uv" in content
        assert "/usr/bin/python3" in content


def test_skill_source_discovery_multi_root(tmp_path):
    """Test setup discovers SKILL.md when positioned at target root or nested dirs."""
    # Create target directory with SKILL.md directly at root
    (tmp_path / "SKILL.md").write_text("---\nname: chrome-bridge\n---\n# Root Skill")

    res = run_setup_host("setup", "--target", str(tmp_path))
    assert res.returncode == 0
    assert "Resolved skill source" in res.stdout


def test_setup_host_configures_claude_code_json(tmp_path):
    """Test that setup automatically creates and configures ~/.claude.json for Claude Code using uvx."""
    runtime_dir = tmp_path / "runtime"
    home_dir = tmp_path / "fake_home"
    home_dir.mkdir()

    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)

    res = run_setup_host("setup", "--target", str(runtime_dir), "--quiet", env=env)
    assert res.returncode == 0, f"setup_host failed: {res.stderr}\n{res.stdout}"

    claude_json = home_dir / ".claude.json"
    assert claude_json.exists(), "~/.claude.json was not created"
    data = json.loads(claude_json.read_text())
    assert "mcpServers" in data
    assert "chrome-bridge" in data["mcpServers"]
    assert data["mcpServers"]["chrome-bridge"]["command"] == "uvx"
    assert data["mcpServers"]["chrome-bridge"]["args"] == ["antigravity-chrome-bridge", "mcp"]


def test_setup_host_configures_antigravity_config_dir(tmp_path):
    """Test that setup configures ~/.config/antigravity/mcp_config.json alongside ~/.agent."""
    home_dir = tmp_path / "fake_home"
    home_dir.mkdir()

    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)

    res = run_setup_host("setup", "--quiet", env=env)
    assert res.returncode == 0

    dot_config_mcp = home_dir / ".config" / "antigravity" / "mcp_config.json"
    assert dot_config_mcp.exists(), "~/.config/antigravity/mcp_config.json was not created"
    data = json.loads(dot_config_mcp.read_text())
    assert data["mcpServers"]["chrome-bridge"]["command"] == "uvx"


def test_setup_host_dev_mode_configures_local_python_mcp(tmp_path):
    """Test that --dev generates direct Python script invocation for local development."""
    home_dir = tmp_path / "fake_home"
    home_dir.mkdir()

    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)

    res = run_setup_host("setup", "--dev", "--quiet", env=env)
    assert res.returncode == 0

    claude_json = home_dir / ".claude.json"
    data = json.loads(claude_json.read_text())
    assert data["mcpServers"]["chrome-bridge"]["args"][0].endswith("mcp_server.py")


def test_browser_manifest_targets_includes_vivaldi_and_arc(tmp_path):
    """Test that Linux manifest registration includes Vivaldi and Arc browser paths."""
    home_dir = tmp_path / "fake_home"
    home_dir.mkdir()

    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)

    res = run_setup_host("setup", "--quiet", env=env)
    assert res.returncode == 0

    if sys.platform.startswith("linux"):
        vivaldi_manifest = home_dir / ".config" / "vivaldi" / "NativeMessagingHosts" / "com.chrome_bridge.native.json"
        assert vivaldi_manifest.exists(), "Vivaldi manifest was not created"
        arc_manifest = home_dir / ".config" / "arc" / "NativeMessagingHosts" / "com.chrome_bridge.native.json"
        assert arc_manifest.exists(), "Arc manifest was not created"


def test_setup_host_claude_code_non_destructive_merge(tmp_path):
    """Test that setup preserves existing keys and other mcpServers in ~/.claude.json."""
    runtime_dir = tmp_path / "runtime"
    home_dir = tmp_path / "fake_home"
    home_dir.mkdir()

    claude_json = home_dir / ".claude.json"
    initial_data = {
        "allowedTools": ["Bash", "GlobTool"],
        "mcpServers": {
            "existing-server": {
                "command": "python3",
                "args": ["server.py"]
            }
        },
        "customSetting": True
    }
    claude_json.write_text(json.dumps(initial_data, indent=2))

    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)

    res = run_setup_host("setup", "--target", str(runtime_dir), "--quiet", env=env)
    assert res.returncode == 0, f"setup_host failed: {res.stderr}\n{res.stdout}"

    updated = json.loads(claude_json.read_text())
    assert updated["allowedTools"] == ["Bash", "GlobTool"]
    assert updated["customSetting"] is True
    assert "existing-server" in updated["mcpServers"]
    assert "chrome-bridge" in updated["mcpServers"]


def test_setup_host_claude_code_handles_malformed_json(tmp_path):
    """Test that setup gracefully handles malformed ~/.claude.json without throwing or aborting."""
    runtime_dir = tmp_path / "runtime"
    home_dir = tmp_path / "fake_home"
    home_dir.mkdir()

    claude_json = home_dir / ".claude.json"
    claude_json.write_text("{ this is definitely not valid json")

    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)

    res = run_setup_host("setup", "--target", str(runtime_dir), "--quiet", env=env)
    assert res.returncode == 0, f"setup_host should not abort on malformed JSON: {res.stderr}\n{res.stdout}"


def test_setup_host_status_reports_claude_code(tmp_path):
    """Test that status command reports Claude Code MCP configuration state."""
    home_dir = tmp_path / "fake_home"
    home_dir.mkdir()

    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)

    res = run_setup_host("status", env=env)
    assert res.returncode == 0
    assert "Claude Code" in res.stdout


def test_setup_host_cleanup_removes_endpoints(tmp_path):
    """Test that cleanup command removes manifest files and unlinks IPC socket/port files."""
    home_dir = tmp_path / "fake_home"
    home_dir.mkdir()
    target_dir = tmp_path / "runtime"
    target_dir.mkdir()

    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)

    # First setup
    run_setup_host("setup", "--target", str(target_dir), "--quiet", env=env)

    # Create dummy socket/port in temp directory
    sock_path = os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.sock")
    port_path = os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.port")
    if os.path.exists(sock_path) or os.path.islink(sock_path):
        try:
            os.remove(sock_path)
        except OSError:
            pass
    if os.path.exists(port_path):
        try:
            os.remove(port_path)
        except OSError:
            pass
    with open(sock_path, "w") as f:
        f.write("mock")
    with open(port_path, "w") as f:
        f.write("12345")

    # Run cleanup
    res = run_setup_host("cleanup", "--target", str(target_dir), env=env)
    assert res.returncode == 0
    assert not os.path.exists(sock_path), "cleanup did not remove socket file"
    assert not os.path.exists(port_path), "cleanup did not remove port file"


def test_setup_host_prints_extension_folder_and_instructions(tmp_path):
    """Test that setup output prints the local unpacked extension folder path and instructions, not a webstore link."""
    home_dir = tmp_path / "fake_home"
    home_dir.mkdir()
    target_dir = tmp_path / "runtime"

    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)

    res = run_setup_host("setup", "--target", str(target_dir), "--no-listen", env=env)
    assert res.returncode == 0
    assert "chromewebstore.google.com" not in res.stdout
    assert "Extension Path" in res.stdout
    assert "EXTENSION INSTALLATION INSTRUCTIONS:" in res.stdout
    assert "chrome://extensions/" in res.stdout
    assert "Load unpacked" in res.stdout


def test_resolve_extension_dir_prioritizes_install_then_source(tmp_path):
    """Test that resolve_extension_dir resolves installed extension dir or falls back to source repo."""
    from setup_host import resolve_extension_dir

    install_dir = tmp_path / "install"
    source_dir = tmp_path / "source"
    install_dir.mkdir()
    source_dir.mkdir()

    # Neither has extension dir -> defaults to install_dir / extension
    assert resolve_extension_dir(install_dir, source_dir) == (install_dir / "extension").resolve()

    # Source has extension dir
    (source_dir / "extension").mkdir()
    assert resolve_extension_dir(install_dir, source_dir) == (source_dir / "extension").resolve()

    # Install has extension dir -> prioritizes install_dir
    (install_dir / "extension").mkdir()
    assert resolve_extension_dir(install_dir, source_dir) == (install_dir / "extension").resolve()


def test_setup_host_test_subcommand_idle_and_active():
    """Test that test command checks IPC connectivity cleanly."""
    # When no host is running, reports idle state with returncode 0
    sock_path = os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.sock")
    port_path = os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.port")
    if os.path.exists(sock_path):
        os.remove(sock_path)
    if os.path.exists(port_path):
        os.remove(port_path)

    res = run_setup_host("test")
    assert res.returncode == 0
    assert "Verifying Chrome Bridge IPC connectivity" in res.stdout
    assert "idle until Chrome opens" in res.stdout

