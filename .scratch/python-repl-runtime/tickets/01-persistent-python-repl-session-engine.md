# 01 — Persistent Python REPL Session Engine & Output Budgeting

**What to build:** An in-memory, stateful Python evaluation engine that enables AI Drivers to run procedural multi-line Python scripts across consecutive conversational turns. Variables, imports, and functions defined in one turn persist into subsequent turns. The engine naturally evaluates trailing expression statements to return their value, captures `sys.stdout` and `sys.stderr` streams, and enforces structural collection pruning (10 items, 10 keys, depth 3) and hard character caps (12,000 chars) with head-and-tail preservation.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Multi-line Python execution engine parses code using AST splitting, executing top-level statements and evaluating trailing expressions.
- [ ] Persistent single-dictionary namespace preserves variables, imports, and helper functions across multiple consecutive executions.
- [ ] Standard streams (`sys.stdout`, `sys.stderr`) are redirected and captured cleanly without leaking to the host process.
- [ ] Output serialization formats results into tagged blocks (`[stdout]`, `[stderr]`, `[result]`, `[error]`).
- [ ] Large collections (lists, tuples) are structurally truncated at 10 items with `... (N more items)`.
- [ ] Dictionaries are pruned at 10 keys and 3 nesting levels with `{... N keys}` and `[... N items]`.
- [ ] Strings and large outputs exceeding 12,000 characters are capped using head-and-tail preservation with explicit omitted token counts.
- [ ] Comprehensive unit test suite (`tests/test_repl_engine.py`) verifies state persistence, stream capture, and formatting contracts.
