# 02 — REPL Engine Traceback Scrubbing

**What to build:**
When an exception is thrown during Python REPL code execution, the returned `[stderr]` / error traceback strictly filters out internal implementation frames (such as socket client communication, JSON serialization, and internal helper routines). The traceback displayed to the Driver only shows the user's `<repl>` lines and public `chrome.*` method calls.

**Blocked by:** 01 — Domain Exception Sanitization & Error Masking

**Status:** ready-for-agent

- [x] `PythonReplSession._sanitize_traceback` strips all internal frames originating from `ChromeSocketClient`, socket networking, and internal dispatchers.
- [x] Error tracebacks preserve `<repl>` execution frames and top-level public `chrome_sdk` entry points.
- [x] Exceptions thrown from user Python code display concise, readable tracebacks without internal clutter.
- [x] Unit tests in `tests/test_repl_engine.py` verify that tracebacks from both user code errors and SDK domain exceptions contain zero internal socket frames.
