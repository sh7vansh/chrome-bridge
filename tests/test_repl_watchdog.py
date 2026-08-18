"""Unit tests for REPL execution watchdog and timeout ceiling."""

import pytest
import time
from repl_engine import PythonReplSession


def test_repl_watchdog_terminates_infinite_loop():
    session = PythonReplSession()
    # Execute an intentional infinite or long loop with a short timeout
    code = """
import time
start = time.time()
while time.time() - start < 5:
    pass
"""
    result = session.execute(code, timeout=0.5)
    assert "[error]" in result
    assert "TimeoutError" in result or "timed out" in result.lower()


def test_repl_watchdog_allows_normal_fast_execution():
    session = PythonReplSession()
    code = "x = 40 + 2\nx"
    result = session.execute(code, timeout=5.0)
    assert "[result]\n42" in result
