# 01 — Cross-Platform IPC Transport Layer & Diagnostic Recovery

**What to build:**
The Python REPL runtime and Node Native Host communicate over dynamically resolved, platform-aware temporary directory paths (`tempfile.gettempdir()` / `os.tmpdir()`) across Linux, macOS, and Windows, replacing hardcoded `/tmp/` paths. When browser communication cannot be established, `BrowserUnavailableError` presents an actionable, sanitized self-check checklist under strict Zero Information Leakage guarantees.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Python SDK dynamically resolves default socket path via `os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.sock")` across operating systems.
- [x] Node Native Host dynamically resolves socket path via `path.join(os.tmpdir(), "antigravity_chrome_bridge.sock")` across operating systems.
- [x] Disconnection errors raise `BrowserUnavailableError` containing clear, actionable self-check items (verify Chrome is running, verify extension is enabled, re-run setup).
- [x] Zero Information Leakage is preserved: no raw socket paths, system filenames, or extension internals are leaked in user-facing tracebacks or error messages.
- [x] Unit tests verify dynamic path resolution across mocked OS environments and validate sanitized error formatting.
