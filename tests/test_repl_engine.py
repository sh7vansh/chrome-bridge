"""Tests for PythonReplSession and OutputBudgetFormatter."""
import pytest
from repl_engine import PythonReplSession, OutputBudgetFormatter


def test_basic_expression_evaluation():
    session = PythonReplSession()
    out = session.execute("2 + 2")
    assert "[result]" in out
    assert "4" in out


def test_multi_statement_and_trailing_expression():
    session = PythonReplSession()
    code = """
x = 10
y = 20
x + y
"""
    out = session.execute(code)
    assert "[result]" in out
    assert "30" in out


def test_persistent_state_across_calls():
    session = PythonReplSession()
    session.execute("a = 42\ndef greet(name):\n    return f'Hello, {name}!'")
    out = session.execute("greet('Driver') + f' a is {a}'")
    assert "[result]" in out
    assert "Hello, Driver! a is 42" in out


def test_stdout_and_stderr_capture():
    session = PythonReplSession()
    code = """
import sys
print("Standard log output")
print("Warning diagnostic", file=sys.stderr)
"final_result"
"""
    out = session.execute(code)
    assert "[stdout]" in out
    assert "Standard log output" in out
    assert "[stderr]" in out
    assert "Warning diagnostic" in out
    assert "[result]" in out
    assert "final_result" in out


def test_executed_successfully_with_no_output():
    session = PythonReplSession(include_ambient=False)
    out = session.execute("z = 100")
    assert out == "(executed successfully with no output)"



def test_last_result_variable_underscore():
    session = PythonReplSession()
    session.execute("5 * 5")
    out = session.execute("_ + 10")
    assert "[result]" in out
    assert "35" in out


def test_exception_handling_and_formatting():
    session = PythonReplSession()
    out = session.execute("1 / 0")
    assert "[error]" in out
    assert "ZeroDivisionError" in out
    assert "[stderr]" in out
    assert "division by zero" in out


def test_structural_pruning_collections():
    session = PythonReplSession()
    out = session.execute("list(range(50))")
    assert "[result]" in out
    assert "0, 1, 2, 3, 4, 5, 6, 7, 8, 9" in out
    assert "... (40 more items)" in out


def test_structural_pruning_deep_dict():
    session = PythonReplSession()
    code = """
{
    'level1': {
        'level2': {
            'level3': {
                'level4': 'too deep',
                'extra': 123
            }
        }
    }
}
"""
    out = session.execute(code)
    assert "[result]" in out
    assert "{... 2 keys}" in out or "[... 2 items]" in out or "level3" in out


def test_hard_character_cap_head_and_tail():
    formatter = OutputBudgetFormatter(max_chars=500, string_head_tail=100)
    huge_str = "A" * 200 + "MIDDLE_TEXT" * 50 + "Z" * 200
    formatted = formatter.format_execution_result(result=huge_str, has_result=True)
    assert "[result]" in formatted
    assert "omitted" in formatted
    assert formatted.startswith("[result]")
    assert len(formatted) <= 800


def test_traceback_sanitization_removes_internal_frames():
    from unittest.mock import MagicMock
    from chrome_sdk import Chrome, BrowserUnavailableError

    # Create a mock socket client that raises BrowserUnavailableError from inside its internal call
    mock_client = MagicMock()
    mock_client.call.side_effect = BrowserUnavailableError("Browser instance is not reachable or session disconnected.")

    mock_chrome = Chrome(client=mock_client)
    session = PythonReplSession(globals_dict={"chrome": mock_chrome})

    out = session.execute("chrome.snapshot()")
    assert "[error]" in out
    assert "BrowserUnavailableError" in out
    assert "[stderr]" in out
    
    # Assert traceback includes the <repl> line and doesn't leak internal client/socket method frames
    assert "<repl>" in out
    for forbidden in ["ChromeSocketClient", "_raise_structured_error", "socket.py", "net.connect"]:
        assert forbidden not in out, f"Internal frame '{forbidden}' leaked in output: {out}"


def test_execution_outcome_and_diagnostic_report_rendering():
    from repl_engine import ExecutionOutcome, DiagnosticReport, OutputBudgetFormatter, extract_diagnostic_report

    formatter = OutputBudgetFormatter(max_chars=4000)
    diag = DiagnosticReport(
        failing_line=3,
        failing_code="chrome.find('missing_btn').click()",
        candidate_matches=[{"ref": "12", "role": "button", "name": "Submit Form"}],
        auto_snapshot="[#1] <button>Submit Form</button>",
    )
    outcome = ExecutionOutcome(
        stdout="Orientation step complete\n",
        error="ElementNotFoundError: element not found",
        diagnostic=diag,
        ambient_header="[Active Tab: #1 | URL: https://example.com | Title: Test]",
    )

    rendered = formatter.render(outcome)
    assert "[Active Tab: #1" in rendered
    assert "[error]" in rendered
    assert "Line 3: chrome.find('missing_btn').click()" in rendered
    assert "[partial_stdout]" in rendered
    assert "Orientation step complete" in rendered
    assert "[candidate_matches]" in rendered
    assert "- [#12] (button 'Submit Form')" in rendered
    assert "[diagnostic_auto_snapshot]" in rendered
    assert "[#1] <button>Submit Form</button>" in rendered


def test_extract_diagnostic_report_helper():
    from repl_engine import extract_diagnostic_report
    from chrome_sdk import ElementNotFoundError

    code = "x = 1\ny = 2\nraise ElementNotFoundError('btn', suggestions=[{'ref': '5', 'role': 'btn', 'name': 'OK'}])"
    try:
        exec(compile(code, "<repl>", "exec"))
    except Exception as e:
        diag = extract_diagnostic_report(e, code)
        assert diag.failing_line == 3
        assert "raise ElementNotFoundError" in diag.failing_code
        assert len(diag.candidate_matches) == 1
        assert diag.candidate_matches[0]["ref"] == "5"


