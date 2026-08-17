# 04 — Single-Turn Self-Healing Diagnostics & Interceptor Detection

**What to build:** Diagnostic feedback mechanisms that enable the AI Driver to self-heal in a single turn without manual re-querying. When an element lookup fails, the extension tracks snapshot history to compute fuzzy near-match candidate suggestions (`Did you mean: [#18] (button 'Submit')?`). When a pointer click is blocked by a modal overlay or sticky banner, `elementFromPoint` detects the interceptor and reports its tag and Ref-ID. On any unhandled action exception, the Python runtime automatically queries and attaches a fresh compact Semantic DOM Snapshot under `[diagnostic_auto_snapshot]`.

**Blocked by:** 03 — Synchronous Python SDK & Polymorphic Locator Dispatch.

**Status:** ready-for-agent

- [ ] Extension maintains historical Ref-ID mapping (`role`, `name`, `tag`, `classes`) across snapshots in page context.
- [ ] On lookup miss for a stale Ref-ID, similarity scoring calculates and returns top candidate suggestions matching role/name.
- [ ] Pointer actions automatically scroll target element to center of viewport (`scrollIntoView`) prior to hit-testing.
- [ ] Intercepted clicks detect overlapping backdrop/banner nodes and raise `ActionInterceptionError` detailing the intercepting element.
- [ ] `NavigationTimeoutError` distinguishes between elements absent from DOM, elements hidden in DOM (`display: none`), and document `readyState`.
- [ ] REPL execution engine catches `ChromeBridgeError` subclasses and automatically injects a fresh `[diagnostic_auto_snapshot]` into the tool response.
- [ ] Tests verify that failed actions produce actionable suggestions, interceptor details, and fresh auto-snapshots.
