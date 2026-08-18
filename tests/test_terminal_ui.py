"""Tests for zero-dependency pure Python TerminalUI and Spinner engine."""

import io
import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

# Import or test TerminalUI directly
from setup_host import TerminalUI


def test_terminal_ui_color_formatting():
    """Test ANSI color formatting and NO_COLOR enforcement."""
    ui = TerminalUI(force_color=True, interactive=True)
    assert "\033[1m" in ui.bold("test")
    assert "\033[32m" in ui.green("success")
    assert "\033[31m" in ui.red("error")
    assert "\033[36m" in ui.cyan("info")

    ui_no_color = TerminalUI(force_color=False, interactive=False)
    assert ui_no_color.bold("test") == "test"
    assert ui_no_color.green("success") == "success"
    assert ui_no_color.red("error") == "error"


def test_terminal_ui_badges():
    """Test status badge rendering."""
    ui = TerminalUI(force_color=True, interactive=True)
    done_badge = ui.badge_done("Configured")
    assert "[DONE]" in done_badge or "✓" in done_badge

    fail_badge = ui.badge_fail("Error")
    assert "[FAIL]" in fail_badge or "✗" in fail_badge

    warn_badge = ui.badge_warn("Warning")
    assert "[WARN]" in warn_badge or "⚠️" in warn_badge


def test_terminal_ui_spinner_ok():
    """Test spinner context manager lifecycle completing with ok."""
    stream = io.StringIO()
    ui = TerminalUI(force_color=True, interactive=True, stream=stream)

    with ui.spinner("Registering manifests") as sp:
        time.sleep(0.1)
        sp.ok("6 manifests registered")

    output = stream.getvalue()
    assert "6 manifests registered" in output


def test_terminal_ui_spinner_fail():
    """Test spinner context manager lifecycle completing with fail."""
    stream = io.StringIO()
    ui = TerminalUI(force_color=True, interactive=True, stream=stream)

    with ui.spinner("Checking permissions") as sp:
        time.sleep(0.05)
        sp.fail("Permission denied")

    output = stream.getvalue()
    assert "Permission denied" in output


def test_terminal_ui_non_interactive_fallback():
    """Test non-interactive / pipe mode does not emit cursor hide/show escapes or rewrite loops."""
    stream = io.StringIO()
    ui = TerminalUI(force_color=False, interactive=False, stream=stream)

    with ui.spinner("Syncing files") as sp:
        time.sleep(0.05)
        sp.ok("Files synced")

    output = stream.getvalue()
    assert "\033[?25l" not in output
    assert "\033[?25h" not in output
    assert "Files synced" in output


def test_terminal_ui_card():
    """Test box-drawn card formatting."""
    ui = TerminalUI(force_color=False, interactive=False)
    card = ui.card("System Status", [
        ("Platform", "Linux x86_64"),
        ("Native Host", "Active (com.chrome_bridge.native)"),
    ])
    assert "System Status" in card
    assert "Platform" in card
    assert "Linux x86_64" in card
    assert "Native Host" in card
