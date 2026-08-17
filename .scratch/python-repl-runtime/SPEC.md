# Specification: Persistent Python REPL Runtime for Chrome Bridge

**Status**: Ready for Agent (`ready-for-agent`)  
**Origin**: Wayfinder Architecture Exploration (`.scratch/python-repl-runtime/map.md`)  
**Domain Model**: [CONTEXT.md](../../CONTEXT.md)  

---

## Problem Statement

When AI agent drivers interact with web browsers using traditional multi-tool MCP architectures (e.g. `chrome_click`, `chrome_type`, `chrome_scroll`, `chrome_get_page_content`), they encounter several severe structural bottlenecks:

1. **Context Window Exhaustion**: Extracting raw HTML or full DOM trees dumps tens of thousands of tokens per turn, consuming context budgets rapidly and inflating latency.
2. **Tool Selection Friction & Hallucination**: Managing 10+ distinct JSON-RPC tools with disjoint schemas leads to tool calling errors, parameter hallucination, and fragile multi-turn loops.
3. **Turn Round-Trip Latency**: Iterative tasks (such as filling a 10-field form, scraping paginated tables, or polling for asynchronous state) require an agent turn for every single action, making workflows slow and expensive.
4. **State Statelessness**: Previous agent commands cannot easily pass intermediate data, dataframes, or element references into subsequent steps without re-querying the browser.
5. **Brittle Error Recovery**: When an element re-renders or an action fails, traditional tools return generic errors, forcing the model to spend an entire extra turn requesting a new page dump before it can retry.

---

## Solution

A stateful, persistent **Python REPL Runtime Layer** embedded inside Chrome Bridge, exposing a single unified MCP tool: `execute_python(code)`.

The AI Driver executes procedural Python scripts that run against an in-memory session. Within this session, a pre-injected synchronous standard library (`chrome`) provides high-level browser control with indexed Ref-IDs (`[#1]`, `[#2]`), distilled Semantic DOM snapshots (99%+ token reduction), dual-layer token budgeting, and single-turn self-healing error diagnostics that auto-inject fresh snapshots on exceptions.

---

## User Stories

1. As an AI Driver, I want a single `execute_python` tool, so that I do not have to select between dozens of separate browser tools with disparate schemas.
2. As an AI Driver, I want Python variables, imports, and functions defined in one turn to persist into future turns, so that I can maintain state, cache data, and write reusable subroutines.
3. As an AI Driver, I want to call `chrome.snapshot()`, so that I receive an ultra-compact Semantic DOM outline with lightweight indexed Ref-IDs instead of a bloated raw HTML tree.
4. As an AI Driver, I want interactive elements to be addressed by polymorphic locators (e.g. integer `14`, Ref-ID string `"[#14]"`, or CSS selector `"button.submit"`), so that I can write ergonomic and flexible automation code.
5. As an AI Driver, I want mutating browser actions (like `chrome.click()` and `chrome.type()`) to return lightweight acknowledgment dicts rather than re-dumping the full DOM, so that I conserve token context in multi-step loops.
6. As an AI Driver, I want to write multi-step loops (such as iterating over table rows or filling multi-field forms) in a single Python script, so that the entire workflow completes in one agent turn.
7. As an AI Driver, I want `sys.stdout` and `sys.stderr` to be captured alongside the final evaluated expression, so that I can use `print()` statements for diagnostic logging.
8. As an AI Driver, I want collections and deeply nested dictionaries returned by my scripts to be structurally pruned, so that massive data structures do not exceed my token budget.
9. As an AI Driver, I want output strings exceeding character limits to be truncated with head-and-tail preservation, so that I see both initial results and concluding summary values without corrupting syntax.
10. As an AI Driver, I want an unhandled action exception (such as `ElementNotFoundError`) to automatically attach a fresh compact Semantic DOM Snapshot in the error block, so that I can self-correct in the very next turn without a separate snapshot call.
11. As an AI Driver, I want stale Ref-IDs to provide fuzzy near-match suggestions based on role and text, so that I immediately know which Ref-ID replaced a mutated DOM element.
12. As an AI Driver, I want pointer clicks to automatically center elements in the viewport before hit-testing, so that off-screen elements do not trigger spurious failures.
13. As an AI Driver, I want obstructed clicks to identify the intercepting overlay or modal element, so that I know exactly which banner or backdrop needs to be dismissed first.
14. As an AI Driver, I want synchronous waiting helpers (`chrome.wait_for(target)` and `chrome.wait_for_url(pattern)`), so that my scripts reliably handle asynchronous page transitions.
15. As an AI Driver, I want scoped `Tab` handles (`chrome.tabs`, `chrome.tab(id)`), so that I can inspect and control multiple browser tabs deterministically.
16. As a human developer, I want standard MCP configuration templates for Antigravity CLI, Claude Desktop, and IDE assistants, so that I can install and run Chrome Bridge with a single command.
17. As a human developer, I want the Python REPL to communicate directly with the Chrome Extension via a local Unix domain socket, so that execution is fast, secure, and has zero external server dependencies.

---

## Implementation Decisions

### 1. REPL Session Engine & Namespace Architecture
- The runtime operates a stateful in-process Python execution engine.
- A single global dictionary is maintained across calls.
- Script parsing utilizes AST splitting: top-level statements are executed sequentially via `exec()`, while a trailing expression statement is evaluated via `eval()` to capture its return value.
- Standard streams (`sys.stdout`, `sys.stderr`) are redirected and captured per execution turn.
- The Python session communicates synchronously with the native messaging socket (`/tmp/chrome_bridge.sock`).

### 2. Semantic DOM Snapshot Engine & Ref-ID Resolution
- Traversal runs in the active page context using a DOM `TreeWalker`.
- Node filtering checks computed visibility (`checkVisibility()`), skipping hidden, zero-sized, and non-interactive boilerplate elements.
- Accessible names are computed following AccName 1.2 principles (`aria-label`, `aria-labelledby`, inner text, `placeholder`, `alt`).
- Interactive elements receive an ephemeral sequential Ref-ID integer (e.g. `[#1]`, `[#2]`).
- Serialized output renders an indented tree outline delivering 99%+ token reduction over raw DOM representations.

### 3. Synchronous Python SDK (`chrome`)
- The `chrome` global singleton delegates to the active browser tab, providing top-level helper methods (`snapshot`, `click`, `type`, `navigate`, `scroll`, `wait_for`, `tabs`).
- Polymorphic locator normalization resolves integer indices, `"[#N]"` tokens, `"#N"`, and standard CSS selectors.
- Tab management uses object-oriented `Tab` handles providing isolated tab control.
- Mutating actions return lightweight status objects (`{"status": "ok", "action": "click", "target": "[#1]"}`).

### 4. Dual-Layer Token Budgeting & Output Serialization
*(Derived from verified logic prototype)*:
- **Layer 1 (Structural Pruning)**:
  - Collections capped at 10 items with `... (N more items)`.
  - Dictionaries capped at 10 keys and 3 nesting levels with `{... N keys}` and `[... N items]`.
  - SDK objects implement custom high-density `__repr__` (e.g. `<Tab id=1 title="..." url="..." active=True>`).
- **Layer 2 (Hard Safety Ceiling)**:
  - Hard limit of 12,000 characters (~3,000 tokens) with Head-and-Tail preservation:
    ```text
    <head text>
    ... [N chars / M tokens omitted] ...
    <tail text>
    ```
- **Tagged Block Layout**:
  - Output is formatted into tagged plaintext sections: `[stdout]`, `[stderr]`, `[result]`, `[error]`, and `[diagnostic_auto_snapshot]`.

### 5. Self-Healing Diagnostics & Error Recovery
- Base exception `ChromeBridgeError` with specialized subclasses: `ElementNotFoundError`, `ActionInterceptionError`, and `NavigationTimeoutError`.
- **Diagnostic Auto-Snapshot**: Unhandled browser action exceptions automatically query a compact Semantic DOM Snapshot and append it to the tool response.
- **Fuzzy Stale Matching**: The extension tracks previous snapshot metadata. When a Ref-ID lookup misses, similarity scores across live nodes generate candidate suggestions: `Did you mean: [#18] (button 'Submit')?`.
- **Hit-Test Diagnostics**: Actions execute `scrollIntoView(center)`. Coordinate hit collisions against modal backdrops or sticky banners report the specific interceptor tag and Ref-ID.
- **Timeout State Introspection**: Timeouts report URL, document `readyState`, and whether the target is absent from DOM or hidden via CSS (`display: none`).

### 6. MCP Server Tool Schema & Packaging
- Single tool definition: `execute_python(code: str) -> str`.
- Built on Python MCP SDK / FastMCP.
- Packaged via `pyproject.toml` with `mcp>=1.0.0` dependency.
- Configuration mappings provided for Antigravity, Claude Desktop, and IDE agents.

---

## Testing Decisions

### Seams & Verification Strategy
- **Primary Top-Level Seam (Tool & Session Invocation)**:
  - Tests will drive `execute_python(code)` and `PythonReplSession.execute(code)` as a black-box interface.
  - Assertions will test observable behavior: stdout capture, return values, variable retention across consecutive turns, output truncation markers, and error recovery diagnostics.
- **What Makes a Good Test**:
  - Tests MUST verify external behavior and contracts (e.g. "Calling `chrome.click(14)` when `#14` is missing raises `ElementNotFoundError` with fuzzy suggestions and auto-injected snapshot").
  - Tests MUST NOT couple to internal AST node structures or internal string buffer pointer offsets.
- **Prior Art**:
  - Existing suite `test-full.mjs` executes full end-to-end multi-step browser scenarios via MCP stdio.
  - New integration tests will run equivalent multi-step Python workflows via `pytest`.

---

## Out of Scope

- **Headless Browser Runner (Puppeteer/Playwright headless engines)**: Chrome Bridge is explicitly built for the user's live, logged-in Google Chrome browser via Native Messaging.
- **Standalone Web GUI Debugger**: The REPL is designed strictly as an MCP runtime for LLM drivers, not a human desktop IDE.
- **Session Macro Caching & Replay**: Macro recording/caching is deferred to a future phase once the core runtime is stabilized.

---

## Further Notes

- All changes maintain full backward compatibility with the existing Native Messaging host protocol (`/tmp/chrome_bridge.sock`).
