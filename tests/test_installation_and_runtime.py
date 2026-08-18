"""Tests for runtime directory resolution, ambient venv discovery, and setup-host registration."""

import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

import chrome_sdk
from chrome_sdk import resolve_runtime_directory, auto_bootstrap_environment


def test_resolve_runtime_directory_cwd(tmp_path):
    """Test resolution prioritizes current working directory when chrome_sdk.py is present."""
    sdk_file = tmp_path / "chrome_sdk.py"
    sdk_file.write_text("# mock sdk")

    with patch("os.getcwd", return_value=str(tmp_path)):
        resolved = resolve_runtime_directory()
        assert resolved == str(tmp_path)


def test_resolve_runtime_directory_fallback_dot_chrome_bridge(tmp_path):
    """Test fallback resolution finds ~/.chrome-bridge when cwd does not contain SDK."""
    dot_bridge = tmp_path / ".chrome-bridge"
    dot_bridge.mkdir()
    (dot_bridge / "chrome_sdk.py").write_text("# mock sdk")

    with patch("os.getcwd", return_value=str(tmp_path / "non_existent_cwd")), \
         patch("os.path.expanduser", side_effect=lambda p: str(dot_bridge) if "~/.chrome-bridge" in p else str(tmp_path / "chrome-bridge")):
        resolved = resolve_runtime_directory()
        assert resolved == str(dot_bridge)


def test_resolve_runtime_directory_fallback_legacy(tmp_path):
    """Test fallback resolution finds legacy ~/chrome-bridge when other paths missing."""
    legacy_bridge = tmp_path / "chrome-bridge"
    legacy_bridge.mkdir()
    (legacy_bridge / "chrome_sdk.py").write_text("# mock sdk")

    with patch("os.getcwd", return_value=str(tmp_path / "non_existent_cwd")), \
         patch("os.path.expanduser", side_effect=lambda p: str(tmp_path / "missing_dot") if "~/.chrome-bridge" in p else str(legacy_bridge)):
        resolved = resolve_runtime_directory()
        assert resolved == str(legacy_bridge)


def test_auto_bootstrap_environment_attaches_posix_site_packages(tmp_path):
    """Test ambient venv site-packages discovery on POSIX systems."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "chrome_sdk.py").write_text("# mock sdk")

    venv_dir = runtime_dir / ".venv"
    sp_dir = venv_dir / "lib" / "python3.11" / "site-packages"
    sp_dir.mkdir(parents=True)

    with patch("sys.platform", "linux"), patch("site.addsitedir") as mock_addsitedir:
        added = auto_bootstrap_environment(target_dir=str(runtime_dir))
        assert str(sp_dir) in added
        mock_addsitedir.assert_called_with(str(sp_dir))


def test_auto_bootstrap_environment_attaches_windows_site_packages(tmp_path):
    """Test ambient venv site-packages discovery on Windows systems."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "chrome_sdk.py").write_text("# mock sdk")

    venv_dir = runtime_dir / ".venv"
    sp_dir = venv_dir / "Lib" / "site-packages"
    sp_dir.mkdir(parents=True)

    with patch("sys.platform", "win32"), patch("site.addsitedir") as mock_addsitedir:
        added = auto_bootstrap_environment(target_dir=str(runtime_dir))
        assert str(sp_dir) in added
        mock_addsitedir.assert_called_with(str(sp_dir))


def test_auto_bootstrap_environment_no_venv(tmp_path):
    """Test auto bootstrap succeeds cleanly without errors when .venv is absent."""
    runtime_dir = tmp_path / "runtime_no_venv"
    runtime_dir.mkdir()
    (runtime_dir / "chrome_sdk.py").write_text("# mock sdk")

    with patch("site.addsitedir") as mock_addsitedir:
        added = auto_bootstrap_environment(target_dir=str(runtime_dir))
        assert added == []
        mock_addsitedir.assert_not_called()
