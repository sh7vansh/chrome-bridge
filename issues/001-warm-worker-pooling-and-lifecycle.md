# Subagent Warm-Worker Pooling & Lifecycle Protocol

**Type:** `wayfinder:grilling` (HITL)  
**Parent:** [Map: Adaptive & Context-Aware Chrome Bridge Architecture](file:///home/shivansh/chrome-bridge/issues/map.md)  
**Status:** Closed  
**Assignee:** Antigravity  
**Blocked by:** None  

## Question

How should the parent agent maintain, reuse, and gracefully recycle a warm `chrome_worker` subagent across multiple user turns in Antigravity CLI — specifically defining the message exchange lifecycle (`invoke_subagent` vs `send_message`), idle wait conventions, turn limits (e.g. 5–8 turns), and tear-down triggers?

## Resolution

1. **Warm Pool Protocol via `send_message`:**
   - The Parent Agent tracks `active_worker_id`, `turn_count`, and `cached_state` in its context.
   - **Initial / Cold Turn:** Parent launches a dedicated subagent via `invoke_subagent` (`TypeName="self"`, `Role="Chrome Worker"`), capturing the returned `conversationID`.
   - **Continuation Turns (Turns 2–6):** Parent reuses the existing worker by dispatching commands with `send_message(Recipient=active_worker_id, Message=...)`, completely avoiding cold-start re-imports and prompt bloat.
2. **Bounded Lifecycle & Recycling Rules:**
   - **Max Turn Limit:** A worker is recycled after a maximum of **6 turns**.
   - **Heavy Workload Branching:** Heavy tasks (e.g. deep scraping, large multi-tab crawling) bypass the warm worker; a fresh worker is spawned for heavy tasks and immediately retired upon completion.
   - **Retirement Execution:** Parent calls `manage_subagents(Action="kill", ConversationIds=[active_worker_id])` and sets `active_worker_id = None`.
3. **Telemetry & State Return:**
   - Every worker response must include a lightweight JSON/markdown telemetry block:
     `{"tab_id": <int>, "url": <str>, "title": <str>, "media_playing": <bool>}`.
   - This keeps the parent's handover cache automatically updated without DOM parsing overhead.
4. **Fault Recovery:**
   - If `send_message` errors or worker state is desynchronized, parent immediately kills the worker and spawns a clean replacement using the latest `cached_state`.
