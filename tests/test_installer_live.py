"""Comprehensive end-to-end test suite for the Smart Live Installer."""

import argparse
import io
import sys
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

import setup_host
from setup_host import (
    run_setup,
    run_status,
    run_doctor,
    main,
    TerminalUI,
)


def test_run_setup_quiet_dev_mode(tmp_path):
    """Test full setup runs cleanly in quiet dev mode without network or browser dependencies."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    install_dir = tmp_path / "install"
    install_dir.mkdir()

    args = argparse.Namespace(
        command="setup",
        dev=True,
        target=str(install_dir),
        quiet=True,
        no_listen=True,
        interactive=False,
    )

    with patch("setup_host.resolve_home_dir", return_value=home_dir), \
         patch("setup_host.resolve_install_dir", return_value=install_dir):
        exit_code = run_setup(args)
        assert exit_code == 0

        # Verify host launcher was generated
        launcher = install_dir / ("native-host.bat" if setup_host.IS_WINDOWS else "native-host.sh")
        assert launcher.exists()


def test_run_status_renders_dashboard(tmp_path):
    """Test status command renders complete dashboard with runtime and browser cards."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    install_dir = tmp_path / "install"
    install_dir.mkdir()

    args = argparse.Namespace(
        command="status",
        dev=False,
        target=str(install_dir),
        quiet=False,
    )

    stream = io.StringIO()
    with patch("setup_host.resolve_home_dir", return_value=home_dir), \
         patch("setup_host.resolve_install_dir", return_value=install_dir), \
         patch("sys.stdout", stream):
        exit_code = run_status(args)
        assert exit_code == 0
        output = stream.getvalue()
        assert "System & Runtime Diagnostics" in output
        assert "Browser Native Messaging Manifests" in output
        assert "AI Agent MCP Configurations" in output


def test_main_cli_dispatch_simulate():
    """Test CLI dispatch for simulate subcommand."""
    repo_root = Path(__file__).resolve().parent.parent
    native_host_py = repo_root / "native_host.py"
    if not native_host_py.exists():
        pytest.skip("native_host.py missing")

    with patch("sys.argv", ["chrome-bridge", "simulate"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0


def test_main_cli_dispatch_doctor(tmp_path):
    """Test CLI dispatch for doctor subcommand."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    install_dir = tmp_path / "install"
    install_dir.mkdir()

    with patch("sys.argv", ["chrome-bridge", "doctor", "--target", str(install_dir), "--quiet"]), \
         patch("setup_host.resolve_home_dir", return_value=home_dir), \
         patch("setup_host.resolve_install_dir", return_value=install_dir), \
         patch("tempfile.gettempdir", return_value=str(tmp_path)):
        with pytest.raises(SystemExit) as exc:
            main()
        # Doctor may exit 0 or 1 depending on whether manifests are present; checking clean execution
        assert exc.value.code in (0, 1)
