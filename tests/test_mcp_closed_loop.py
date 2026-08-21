"""Unit tests for MCP Closed-Loop Architecture, Ambient Headers, Diagnostics, and Tool Schema."""
import pytest
from unittest.mock import MagicMock
from repl_engine import PythonReplSession, OutputBudgetFormatter
from chrome_sdk import Chrome, Tab, ElementNotFoundError, ChromeBridgeError
import mcp_server


def test_ambient_header_formatting():
    client = MagicMock()
    # Mock list_tabs and media status
    client.call.side_effect = lambda action, params=None, timeout=None: {
        "list_tabs": [{"id": 4, "title": "Dashboard", "url": "https://app.example.com", "active": True}],
        "execute_script": {"found": False, "playbackState": "none"},
        "ping": {"status": "ok"},
    }.get(action, {})

    mock_chrome = Chrome(client=client)
    session = PythonReplSession(globals_dict={"chrome": mock_chrome}, include_ambient=True)
    
    out = session.execute("x = 10\nprint('Computed x:', x)")
    assert "[Active Tab: #4 | URL: https://app.example.com | Title: Dashboard | Media: none]" in out
    assert "[stdout]" in out
    assert "Computed x: 10" in out


def test_ambient_header_empty_script_output():
    client = MagicMock()
    client.call.side_effect = lambda action, params=None, timeout=None: {
        "list_tabs": [{"id": 1, "title": "Google", "url": "https://google.com", "active": True}],
        "execute_script": {"found": True, "paused": False, "title": "Song Title", "artist": "Artist Name", "playbackState": "playing"},
        "ping": {"status": "ok"},
    }.get(action, {})

    mock_chrome = Chrome(client=client)
    session = PythonReplSession(globals_dict={"chrome": mock_chrome}, include_ambient=True)
    
    out = session.execute("a = 50")
    assert "[Active Tab: #1 | URL: https://google.com | Title: Google | Media: playing ('Song Title')]" in out
    assert "(executed successfully with no output)" in out


def test_repl_session_defaults_to_include_ambient():
    client = MagicMock()
    client.call.side_effect = lambda action, params=None, timeout=None: {
        "list_tabs": [{"id": 2, "title": "Portal", "url": "https://portal.example.com", "active": True}],
        "execute_script": {"found": False, "playbackState": "none"},
        "ping": {"status": "ok"},
    }.get(action, {})

    mock_chrome = Chrome(client=client)
    # Instantiate session with default kwargs (include_ambient omitted)
    session = PythonReplSession(globals_dict={"chrome": mock_chrome})
    assert session.include_ambient is True
    out = session.execute("val = 42")
    assert "[Active Tab: #2 | URL: https://portal.example.com | Title: Portal | Media: none]" in out
    assert "(executed successfully with no output)" in out


def test_diagnostic_error_recovery_with_line_and_partial_stdout():
    client = MagicMock()
    client.call.side_effect = lambda action, params=None, timeout=None: {
        "list_tabs": [{"id": 1, "title": "Test Page", "url": "https://example.com", "active": True}],
        "execute_script": None,
    }.get(action, {})

    mock_chrome = Chrome(client=client)
    session = PythonReplSession(globals_dict={"chrome": mock_chrome}, include_ambient=True)

    code = """from chrome_sdk import ElementNotFoundError
print("Step 1: Initializing workflow")
print("Step 2: Performing preliminary calculation")
raise ElementNotFoundError(
    target="Submit Button",
    tab_id=1,
    stale=False,
    suggestions=[{"ref": "#12", "role": "button", "name": "Submit Order"}, {"ref": "#15", "role": "button", "name": "Send"}],
    url="https://example.com"
)
print("Step 3: Should not reach here")
"""
    out = session.execute(code)

    assert "[error]" in out
    assert "Line 4: raise ElementNotFoundError(" in out or "Line 4:" in out
    assert "ElementNotFoundError" in out
    assert "[partial_stdout]" in out
    assert "Step 1: Initializing workflow" in out
    assert "Step 2: Performing preliminary calculation" in out
    assert "Step 3" not in out
    assert "[candidate_matches]" in out
    assert "[#12] (button 'Submit Order')" in out
    assert "[#15] (button 'Send')" in out


def test_mcp_tool_description_and_schema_recipes():
    # Verify TOOL_DESCRIPTION contains key closed loop API patterns
    desc = mcp_server.TOOL_DESCRIPTION
    assert "chrome.find_" in desc or "find_text" in desc or "find_button" in desc
    assert "fill_form" in desc
    assert "extract_items" in desc
    assert "search" in desc
    assert "chrome.media." in desc

    # Verify FastMCP system instructions embed the 4 core recipes
    instructions = mcp_server.mcp.instructions or ""
    assert "Search & Scrape" in instructions
    assert "Form Fill & Submit" in instructions
    assert "Table / List Extraction" in instructions or "Table/List Extraction" in instructions
    assert "extract_items" in instructions
    assert "Media Control" in instructions



def test_mcp_execute_python_wrapper():
    # Test mcp_server.execute_python function
    res = mcp_server.execute_python("100 * 2")
    assert "[result]" in res
    assert "200" in res


def test_output_budget_formatter_structured_sections():
    formatter = OutputBudgetFormatter()
    out = formatter.format_execution_result(
        stdout="Intermediate output",
        error="ElementNotFoundError: not found",
        candidate_matches=[{"ref": "#5", "role": "button", "name": "Confirm"}],
        failing_line=3,
        failing_code="chrome.find_button('Save').click()",
        ambient_header="[Active Tab: #1 | URL: https://example.com | Title: Test | Media: none]",
    )

    assert out.startswith("[Active Tab: #1 | URL: https://example.com | Title: Test | Media: none]")
    assert "[error]" in out
    assert "Line 3: chrome.find_button('Save').click()" in out
    assert "[partial_stdout]" in out
    assert "Intermediate output" in out
    assert "[candidate_matches]" in out
    assert "- [#5] (button 'Confirm')" in out


def test_output_budget_formatter_strict_section_ordering():
    formatter = OutputBudgetFormatter()
    out = formatter.format_execution_result(
        stdout="Intermediate output",
        error="ElementNotFoundError: not found",
        candidate_matches=[{"ref": "#5", "role": "button", "name": "Confirm"}],
        auto_snapshot="<div role='main'>...</div>",
        failing_line=3,
        failing_code="chrome.find_button('Save').click()",
        ambient_header="[Active Tab: #1 | URL: https://example.com | Title: Test | Media: none]",
    )

    error_idx = out.index("[error]")
    stdout_idx = out.index("[partial_stdout]")
    matches_idx = out.index("[candidate_matches]")
    snapshot_idx = out.index("[diagnostic_auto_snapshot]")

    assert error_idx < stdout_idx < matches_idx < snapshot_idx

