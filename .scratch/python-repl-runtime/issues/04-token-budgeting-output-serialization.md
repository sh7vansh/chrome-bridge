Type: prototype
Status: closed
Assignee: antigravity
Blocked by: 03

## Question

How should the Python REPL format, pretty-print, and cap output payloads (dataframes, dicts, lists, DOM element summaries) to enforce hard token limits while preserving high-fidelity information?

## Findings

Complete specification and logic model verified via interactive prototype.
- **Prototype Asset**: [.scratch/python-repl-runtime/token_budget_demo.html](../token_budget_demo.html)
- **Detailed Specification**: [04-token-budgeting-output-serialization.md](../research/04-token-budgeting-output-serialization.md)

Key decisions:
1. **Tagged Section Layout**: Clean format with `[stdout]`, `[stderr]`, `[result]`, `[error]` tagged blocks for LLM consumption.
2. **Dual-Layer Budgeting**:
   - Layer 1 (Structural): Depth cap (3), collection length cap (10 items) with `... (N more items)`, dict key cap (10 keys).
   - Layer 2 (Hard Character Ceiling): 12,000 chars default (~3,000 tokens) with Head-and-Tail preservation and explicit omitted token counts.
3. **Custom Object Repr**: High-density `<Tab id=...>` and action status serialization.

