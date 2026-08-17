"""Unit tests for diagnostic errors and single-turn self-healing."""
import pytest
from repl_engine import PythonReplSession
from chrome_sdk import (
    ChromeBridgeError,
    ElementNotFoundError,
    ActionInterceptionError,
    NavigationTimeoutError,
)


def test_element_not_found_error_with_fuzzy_suggestions():
    err = ElementNotFoundError(
        target="[#14]",
        tab_id=1,
        stale=True,
        suggestions=[{"ref": "#18", "role": "button", "name": "Checkout"}],
        url="https://store.example.com/cart"
    )
    assert "Element matching '[#14]' not found in tab 1" in str(err)
    assert "DOM mutated" in str(err)
    assert "Did you mean: [#18] (button 'Checkout')?" in str(err)


def test_action_interception_error_details():
    err = ActionInterceptionError(
        target="[#5]",
        interceptor_tag="div.modal-backdrop",
        interceptor_ref="99",
        interceptor_desc="Cookie Consent Overlay",
        tab_id=1
    )
    assert "Click on target '[#5]' was intercepted by overlapping element" in str(err)
    assert "[#99] (Cookie Consent Overlay)" in str(err)


def test_navigation_timeout_error_introspection():
    err = NavigationTimeoutError(
        target="button.submit",
        timeout=10.0,
        url="https://example.com/login",
        ready_state="complete",
        dom_state="hidden in DOM (display: none)",
        tab_id=1
    )
    assert "Timed out after 10.0s waiting for 'button.submit'" in str(err)
    assert "hidden in DOM (display: none)" in str(err)


def test_url_timeout_error_introspection():
    err = NavigationTimeoutError(
        target="https://example.com/dashboard*",
        timeout=15.0,
        url="https://example.com/login",
        ready_state="interactive",
        dom_state="unknown",
        tab_id=2
    )
    assert "Timed out after 15.0s waiting for 'https://example.com/dashboard*'" in str(err)
    assert "Current URL: https://example.com/login" in str(err)
    assert "readyState: 'interactive'" in str(err)


def test_repl_auto_injects_diagnostic_snapshot_on_error():
    session = PythonReplSession()
    code = """
from chrome_sdk import ElementNotFoundError
raise ElementNotFoundError(
    target="[#14]",
    tab_id=1,
    stale=True,
    suggestions=[{'ref': '#18', 'role': 'button', 'name': 'Submit'}],
    url="https://example.com"
)
"""
    out = session.execute(code)
    assert "[error]" in out
    assert "ElementNotFoundError" in out
    assert "Did you mean: [#18] (button 'Submit')?" in out


def test_navigation_timeout_error_with_auto_snapshot():
    err = NavigationTimeoutError(
        target="[#99]",
        timeout=5.0,
        url="https://app.example.com",
        ready_state="complete",
        dom_state="absent from DOM",
        tab_id=1
    )
    err.auto_snapshot = "PAGE: \"Dashboard\" (https://app.example.com)\n- heading \"Dashboard\"\n- button [#1] \"Logout\""
    
    session = PythonReplSession()
    out = session.formatter.format_execution_result(
        error=str(err),
        auto_snapshot=err.auto_snapshot
    )
    assert "[error]" in out
    assert "Timed out after 5.0s waiting for '[#99]'" in out
    assert "[diagnostic_auto_snapshot]" in out
    assert "PAGE: \"Dashboard\"" in out
    assert "button [#1] \"Logout\"" in out

