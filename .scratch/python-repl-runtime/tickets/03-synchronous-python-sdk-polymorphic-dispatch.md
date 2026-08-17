# 03 — Synchronous Python SDK & Polymorphic Locator Dispatch

**What to build:** A synchronous, high-ergonomics Python standard library (`chrome`) injected into every REPL session namespace. It exposes top-level methods delegating to the active tab, normalizes polymorphic locators (e.g. integer `14`, token string `"[#14]"` / `"#14"`, or CSS selectors `"button.submit"`), provides object-oriented `Tab` handles (`chrome.tabs`, `chrome.tab(id)`), executes browser actions (`snapshot`, `click`, `type`, `scroll`, `wait_for`, `navigate`, `eval_js`, `screenshot`), and communicates synchronously over `/tmp/chrome_bridge.sock`.

**Blocked by:** 01 — Persistent Python REPL Session Engine & Output Budgeting, 02 — Extension Semantic DOM Snapshot & Indexed Ref-ID Registry.

**Status:** ready-for-agent

- [ ] Python socket client establishes synchronous IPC with `/tmp/chrome_bridge.sock` supporting request IDs and timeouts.
- [ ] Locator normalizer transforms integers, `"[#N]"`, `"#N"`, and CSS selector strings into structured IPC payload targets.
- [ ] Top-level `chrome` singleton exposes active tab automation: `snapshot()`, `click(target)`, `type(target, text)`, `scroll(x, y)`, `wait_for(target)`, `navigate(url)`, `back()`, `forward()`, `reload()`.
- [ ] `Tab` class provides scoped tab instances with tab properties (`info`, `activate()`, `close()`, `navigate()`, `click()`, `type()`).
- [ ] `chrome.tabs` returns a list of scoped `Tab` handles, with custom `__repr__` formatting (`<Tab id=1 title="..." url="..." active=True>`).
- [ ] Mutating actions return lightweight status dictionaries (`{"status": "ok", "action": "click", "target": "[#1]"}`).
- [ ] Automated tests verify polymorphic locator resolution and end-to-end SDK action execution over socket IPC.
