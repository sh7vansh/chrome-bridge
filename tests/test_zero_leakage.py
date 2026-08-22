"""End-to-end integration and zero-information-leakage test suite."""
import pytest
from unittest.mock import MagicMock
from repl_engine import PythonReplSession
from chrome_sdk import (
    Chrome,
    BrowserUnavailableError,
    ElementNotFoundError,
    ActionInterceptionError,
    NavigationTimeoutError,
)

FORBIDDEN_LEAKAGE_TERMS = [
    "extension",
    "socket",
    "/tmp/",
    "native-host",
    "manifest",
    "ChromeSocketClient",
    "json-rpc",
    "callChrome",
    "net.connect",
    "_raise_structured_error",
]


def assert_zero_leakage(text: str, context: str = ""):
    """Assert that text contains none of the forbidden transport or extension terms."""
    lower_text = text.lower()
    for term in FORBIDDEN_LEAKAGE_TERMS:
        assert term.lower() not in lower_text, (
            f"Zero leakage violation in {context}: found forbidden term '{term}' in:\n{text}"
        )


def test_multi_turn_state_persistence_and_zero_leakage():
    mock_client = MagicMock()

    def mock_call(action, params=None, timeout=15.0):
        if action == "list_tabs":
            return [{"id": 1, "title": "Dashboard", "url": "https://example.com", "active": True}]
        if action in ("get_page_content", "snapshot"):
            return {"snapshot": 'PAGE: "Dashboard"\n- button [#1] "Submit"\n- a [#2] "Docs"', "totalInteractive": 2}
        if action == "click":
            return {"status": "ok", "action": "click", "target": "[#1]"}
        return {}

    mock_client.call.side_effect = mock_call
    mock_chrome = Chrome(client=mock_client)
    session = PythonReplSession(globals_dict={"chrome": mock_chrome})

    # Turn 1: Define state and reusable helper
    turn1_out = session.execute("""
data_store = []
def record(action_name, target):
    data_store.append({"action": action_name, "target": target})
    return f"Recorded {action_name} on {target}"

record("init", "page")
""")
    assert "[result]" in turn1_out
    assert "Recorded init on page" in turn1_out
    assert_zero_leakage(turn1_out, "Turn 1 output")

    # Turn 2: Inspect snapshot
    turn2_out = session.execute("""
snap = chrome.snapshot()
print("Inspected snapshot:")
print(snap)
""")
    assert "[stdout]" in turn2_out
    assert "- button [#1] \"Submit\"" in turn2_out
    assert_zero_leakage(turn2_out, "Turn 2 output")

    # Turn 3: Interact and use state from Turn 1
    turn3_out = session.execute("""
res = chrome.click(1)
record("click", 1)
data_store
""")
    assert "[result]" in turn3_out
    assert "init" in turn3_out
    assert "click" in turn3_out
    assert_zero_leakage(turn3_out, "Turn 3 output")


def test_disconnected_browser_error_zero_leakage():
    mock_client = MagicMock()
    mock_client.call.side_effect = BrowserUnavailableError("Browser instance is not reachable or session disconnected.")

    mock_chrome = Chrome(client=mock_client)
    session = PythonReplSession(globals_dict={"chrome": mock_chrome})

    out = session.execute("chrome.snapshot()")
    assert "[error]" in out
    assert "BrowserUnavailableError" in out
    assert "Browser instance is not reachable or session disconnected." in out
    assert_zero_leakage(out, "Disconnected browser error")


def test_element_not_found_auto_snapshot_zero_leakage():
    mock_client = MagicMock()

    def mock_call(action, params=None, timeout=15.0):
        if action == "list_tabs":
            return [{"id": 1, "title": "App", "url": "https://example.com/app", "active": True}]
        if action == "click":
            raise ElementNotFoundError(
                target="[#99]",
                tab_id=1,
                stale=True,
                suggestions=[{"ref": 18, "role": "button", "name": "Submit"}],
                url="https://example.com/app",
            )
        if action in ("get_page_content", "snapshot"):
            return {"snapshot": 'PAGE: "App"\n- button [#18] "Submit"', "totalInteractive": 1}
        return {}

    mock_client.call.side_effect = mock_call
    mock_chrome = Chrome(client=mock_client)
    session = PythonReplSession(globals_dict={"chrome": mock_chrome})

    out = session.execute("chrome.click(99)")
    assert "[error]" in out
    assert "ElementNotFoundError" in out
    assert "Did you mean: [#18] (button 'Submit')?" in out
    assert "[diagnostic_auto_snapshot]" in out
    assert "- button [#18] \"Submit\"" in out
    assert_zero_leakage(out, "ElementNotFoundError recovery output")


def test_action_interception_error_zero_leakage():
    mock_client = MagicMock()
    err = ActionInterceptionError(
        target="[#2]",
        interceptor_tag="div.modal-backdrop",
        interceptor_ref="[#80]",
        interceptor_desc="Cookie Consent Overlay",
        tab_id=1,
    )
    mock_client.call.side_effect = err

    mock_chrome = Chrome(client=mock_client)
    session = PythonReplSession(globals_dict={"chrome": mock_chrome})

    out = session.execute("chrome.click(2)")
    assert "[error]" in out
    assert "ActionInterceptionError" in out
    assert "[#80] (Cookie Consent Overlay)" in out
    assert_zero_leakage(out, "ActionInterceptionError output")


def test_syntax_and_logic_error_traceback_zero_leakage():
    session = PythonReplSession(include_ambient=False)

    # Syntax Error
    syntax_out = session.execute("def broken(:")
    assert "[error]" in syntax_out
    assert "SyntaxError" in syntax_out
    assert_zero_leakage(syntax_out, "SyntaxError output")

    # Runtime ZeroDivisionError
    runtime_out = session.execute("""
def divide(a, b):
    return a / b

divide(10, 0)
""")
    assert "[error]" in runtime_out
    assert "ZeroDivisionError" in runtime_out
    assert "<repl>" in runtime_out
    assert_zero_leakage(runtime_out, "ZeroDivisionError output")


def test_media_fastpath_zero_leakage():
    mock_client = MagicMock()
    mock_client.call.return_value = {
        "found": True,
        "paused": False,
        "currentTime": 10.0,
        "duration": 200.0,
        "volume": 1.0,
        "muted": False,
        "title": "Song Title",
        "artist": "Artist Name",
        "playbackState": "playing",
    }

    mock_chrome = Chrome(client=mock_client)
    session = PythonReplSession(globals_dict={"chrome": mock_chrome})

    out = session.execute("chrome.media.status()")
    assert "[result]" in out
    assert "Song Title" in out
    assert_zero_leakage(out, "chrome.media.status() output")
