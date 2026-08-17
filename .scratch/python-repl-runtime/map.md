## Destination

A complete Technical Specification & Architecture Blueprint for a persistent Python REPL runtime layer in Chrome Bridge, exposing a single `execute_python(code)` MCP tool with a synchronous `chrome` SDK, token-distilled Semantic DOM snapshots, and self-healing diagnostics.

## Notes

- Domain: [CONTEXT.md](../../CONTEXT.md)
- Skills to consult: `domain-modeling`, `grilling`, `research`, `prototype`
- Tracker: Local Markdown tracker (`.scratch/python-repl-runtime/issues/`)
- Principles: Driver (model) controls Chrome strictly via high-level Python code; token minimization over raw dumps; persistent state across turns.

## Decisions so far

- [Python REPL Session Engine](issues/01-python-repl-session-engine.md) — AST-splitting interactive execution model with persistent single-dictionary namespace, stdio stream redirection, and synchronous Unix socket client (/tmp/chrome_bridge.sock) for FastMCP.
- [Semantic DOM Snapshot & Ref-ID Resolution](issues/02-semantic-dom-snapshot-ref-id.md) — In-page TreeWalker traversal with AccName 1.2 name computation, indexed [#ref] registry in page window, and indented outline serialization delivering 99%+ token reduction over raw DOM.
- [Chrome Python SDK API Surface](issues/03-chrome-python-sdk-api-surface.md) — Hybrid global/Tab SDK with polymorphic locators (int/[#N]/CSS), explicit snapshotting, lightweight action acknowledgments, and synchronous wait helpers.
- [Token Budgeting & Output Serialization](issues/04-token-budgeting-output-serialization.md) — Dual-layer serialization engine with structural collection/depth pruning and 12,000-char head/tail budget ceiling formatted in tagged [stdout]/[stderr]/[result] sections.
- [Error Recovery & Diagnostic Feedback](issues/05-error-recovery-diagnostic-feedback.md) — Single-turn self-healing protocol with auto-injected diagnostic snapshots, stale Ref-ID fuzzy near-match suggestions, interceptor hit-test detection, and DOM-state timeout introspection.
- [MCP Server Tool Spec & Config Migration](issues/06-mcp-server-tool-spec-and-config.md) — Single execute_python MCP tool architecture on FastMCP, client configuration mappings, and pyproject.toml packaging.

## Not yet specified

- **Progress Streaming & Long-Running Subroutines**: Specifying how scripts running long scraping loops or polling routines emit intermediate progress updates back to the client.
- **Session Macro Caching & Replay**: Specifying a mechanism to record, name, and replay common multi-step automation macros without regenerating Python code.

## Out of scope

- **Headless Browser Runner (Puppeteer/Playwright headless engines)**: This effort strictly controls the user's active everyday Chrome browser with logged-in profiles via Native Messaging.
- **Standalone Web GUI Debugger**: The REPL interface is designed strictly as an MCP runtime for LLM drivers, not a human desktop IDE.
