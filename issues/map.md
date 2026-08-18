# Map: Adaptive & Context-Aware Chrome Bridge Architecture

## Destination

A locked architectural specification and protocol for Chrome Bridge Adaptive Lifecycle & Context-Aware Worker Routing — achieving < 2s response times for warm continuations, zero context bloat through bounded recycling, lossless state handover across fresh workers, and robust native API fast-paths for SPAs.

**Canonical Spec:** [Spec: Adaptive & Context-Aware Chrome Bridge Architecture](file:///home/shivansh/chrome-bridge/issues/spec-adaptive-context-aware-architecture.md) (`ready-for-agent`)

## Notes

- **Domain:** Antigravity AI Agent Orchestration, Chrome Extension Native Messaging IPC, Python REPL Engine.
- **Consult Skills:** `chrome-bridge`, `agy-customizations`, `antigravity-guide`.
- **Core Rule:** Maintain zero DOM leakage to parent context while preserving multi-turn conversational pronouns and tab context.

## Decisions so far

<!-- the index — one line per closed ticket: enough to judge relevance, then zoom the link for the detail the ticket holds -->

- [Subagent Warm-Worker Pooling & Lifecycle Protocol](file:///home/shivansh/chrome-bridge/issues/001-warm-worker-pooling-and-lifecycle.md) — 6-turn warm worker reuse via `send_message`, instant recycling on heavy workloads, and automatic telemetry state return on each step.
- [Lean State Handover Payload & Session Memory Schema](file:///home/shivansh/chrome-bridge/issues/002-lean-state-handover-schema.md) — 5-line structured markdown context block injected into fresh workers with pre-resolved pronoun intents and direct tab ID binding.
- [Native Media & SPA Fast-Path API Design in `chrome_sdk`](file:///home/shivansh/chrome-bridge/issues/003-native-fast-paths-and-media-api.md) — First-class `chrome.media.*` controller bypassing DOM snapshots via Shadow-DOM traversal and `navigator.mediaSession` APIs (Asset: [`media_fastpath_prototype.py`](file:///home/shivansh/chrome-bridge/issues/assets/media_fastpath_prototype.py)).
- [Zero-Config SDK Path Resolution & Environment Auto-Bootstrap](file:///home/shivansh/chrome-bridge/issues/004-zero-config-sdk-path-bootstrap.md) — 3-tier environment bootstrap via `pip install -e .`, skill preamble path injection, and MCP server runtime directory resolution.

## Not yet specified

- **Dynamic Token-Budget Heuristics:** Exact token thresholds (e.g., sliding window vs raw DOM payload size) triggering automatic worker recycling mid-workflow.
- **Multi-Window & Multi-Profile Tab Multiplexing:** Handling multi-profile Chrome routing when user has multiple browser windows open.
- **Self-Healing Selector Fallback Hierarchy for SPAs:** Tiered recovery strategy when native fast-path fails (e.g., custom web components / canvas players).

## Out of scope

- Direct headless Chrome DevTools Protocol (CDP) replacement (Chrome Bridge remains extension & native-messaging based).
- Full browser profile virtualization or multi-user proxy routing.
