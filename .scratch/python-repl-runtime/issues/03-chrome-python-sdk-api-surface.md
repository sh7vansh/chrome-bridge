Type: grilling
Status: closed
Assignee: antigravity
Blocked by: 01, 02

## Question

What is the exact class design, method signatures, locator syntax, and return types of the synchronous `chrome` Python standard library injected into the REPL?

## Findings

Full API surface specification and class definitions recorded in [03-chrome-python-sdk-api-surface.md](../research/03-chrome-python-sdk-api-surface.md).
Key decisions:
1. **Polymorphic Locator**: Accepts integer (`1`), Ref-ID string (`"[#1]"`), or CSS selector (`"button.submit"`).
2. **Explicit Snapshotting**: Mutating actions return lightweight status dicts (`{"status": "ok", "target": "[#1]"}`); page DOM inspected via explicit `chrome.snapshot()`.
3. **Hybrid Model**: Top-level `chrome` singleton delegates to active tab; `Tab` objects (`chrome.tab(id)`, `chrome.tabs`) provide scoped handles for multi-tab automation.
4. **Deterministic Synchronization**: Synchronous `chrome.wait_for(target)` and `chrome.wait_for_url(pattern)` helpers.

