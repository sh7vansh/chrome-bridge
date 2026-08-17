# 01 — Domain Exception Sanitization & Error Masking

**What to build:**
When browser connection attempts fail, drop, or encounter transport issues, the Python SDK raises a clean `BrowserUnavailableError` instead of raw socket or transport errors. All error messages across the SDK are sanitized to eliminate any reference to Chrome extensions, Manifest V3, Unix domain sockets (`/tmp/chrome_bridge.sock`), or native messaging hosts.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] `BrowserUnavailableError` is defined as a first-class domain exception subclassing `ChromeBridgeError`.
- [x] Socket connection failures and timeouts in `ChromeSocketClient` raise `BrowserUnavailableError` with clear, user-friendly messages like `"Browser instance is not reachable or session disconnected"`.
- [x] All error strings across `chrome_sdk.py` are scrubbed of any mention of `"extension"`, `"socket"`, `"/tmp/"`, `"native-host"`, or `"manifest"`.
- [x] Unit tests in `tests/test_chrome_sdk.py` verify that disconnected state raises `BrowserUnavailableError` with sanitized messaging.
