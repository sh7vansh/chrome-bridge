# Lean State Handover Payload & Session Memory Schema

**Type:** `wayfinder:grilling` (HITL)  
**Parent:** [Map: Adaptive & Context-Aware Chrome Bridge Architecture](file:///home/shivansh/chrome-bridge/issues/map.md)  
**Status:** Closed  
**Assignee:** Antigravity  
**Blocked by:** None  

## Question

What minimal state schema (`tab_id`, `active_url`, `page_title`, `media_state`, `last_interacted_element`) must be maintained in the parent context and injected into new workers when spinning up fresh subagents, ensuring seamless pronoun resolution ("pause it", "close this tab") without bloating the subagent with raw DOM transcripts?

## Resolution

1. **Deterministic Injected Context Block:**
   When spawning a fresh worker (or resetting workers post-recycle), the Parent Agent injects a standardized 5-line markdown context header into the worker's prompt:
   ```markdown
   ### 🌐 Active Browser Context:
   - **Active Tab ID:** <tab_id>
   - **URL:** <current_url>
   - **Page Title:** <page_title>
   - **Media State:** <Playing|Paused|None> (<HTML5 media details>)
   - **Resolved Intent:** <Explicit intent formulated by parent>
   ```

2. **Parent Pronoun Resolution:**
   - The Parent Agent resolves conversational ambiguities (e.g. "mute it", "go back", "click next") against the cached state before passing the prompt to the subagent.
   - Eliminates blind tab discovery or transcript replaying.

3. **Direct Tab Binding:**
   - Fresh workers bind directly to `chrome.get_tab(tab_id)` (or `chrome.active_tab` fallback if cache is empty), achieving instant readiness.
