Type: grilling
Status: closed
Assignee: antigravity
Blocked by: 03

## Question

What is the diagnostic protocol for browser action failures (e.g. element not found, navigation timeout, obscured click) to deliver actionable suggestions and near-matches for LLM driver self-healing?

## Findings

Full diagnostic and recovery specification recorded in [05-error-recovery-diagnostic-feedback.md](../research/05-error-recovery-diagnostic-feedback.md).

Key decisions:
1. **Diagnostic Auto-Snapshot**: Automatic injection of compact Semantic DOM Snapshot under `[diagnostic_auto_snapshot]` on unhandled browser exceptions for single-turn Driver self-healing.
2. **Stale Ref-ID Fuzzy Suggestions**: Historical snapshot tracking in page context computes candidate matches (role, accessible name, Levenshtein distance) when an element is stale.
3. **Action Interception & Auto-Scroll**: Automatic `scrollIntoView(center)` prior to hit testing; detailed reporting of overlay/backdrop interceptor element tag and Ref-ID on blocked coordinates.
4. **Timeout Introspection**: State verification distinguishing between unrendered elements, elements hidden in DOM (`display: none`), and in-progress navigation `readyState`.

