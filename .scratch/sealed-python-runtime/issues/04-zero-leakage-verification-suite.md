# 04 — End-to-End Zero-Leakage Verification Suite

**What to build:**
A comprehensive end-to-end integration test suite verifying that stateful multi-turn Python sessions, multi-step subroutines, self-healing diagnostics, and error responses never leak implementation keywords (`"extension"`, `"socket"`, `"/tmp/"`, `"native-host"`, `"manifest"`) under any execution conditions.

**Blocked by:** 03 — MCP Server Instructions & Skill Documentation Encapsulation

**Status:** ready-for-agent

- [x] Comprehensive test suite in `tests/test_zero_leakage.py` executing realistic multi-turn agent scripts against `PythonReplSession`.
- [x] Leakage assertion fixtures verifying that all output strings, error dictionaries, and exceptions are free of forbidden transport/extension tokens.
- [x] Verify state persistence across turns (variables, functions, imported modules).
- [x] Verify that diagnostic auto-snapshots attach correctly to domain exceptions without leaking socket frames.
- [x] All existing test suites pass cleanly (`pytest tests/`).
