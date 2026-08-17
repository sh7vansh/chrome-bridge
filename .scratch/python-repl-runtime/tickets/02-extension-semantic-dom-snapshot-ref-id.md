# 02 — Extension Semantic DOM Snapshot & Indexed Ref-ID Registry

**What to build:** Upgraded Chrome extension content script and background message handlers that traverse the live web page DOM using `document.createTreeWalker()` to generate a token-distilled Semantic DOM Snapshot. The snapshot filters computed visibility (`checkVisibility`), computes accessible names following AccName 1.2 rules (`aria-label`, inner text, `placeholder`, `alt`), assigns ephemeral indexed Ref-IDs (`[#1]`, `[#2]`) stored in `window.__chrome_bridge_refs`, and returns an indented outline delivering 99%+ token reduction over raw DOM HTML.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Content script implements a TreeWalker traversal that skips invisible elements (`checkVisibility`), zero-dimension nodes, and script/style tags.
- [ ] Accessible name computation accurately resolves `aria-labelledby`, `aria-label`, inner text, placeholders, tooltips, and image alt text.
- [ ] Interactive elements (links, buttons, inputs, selects, textareas, contenteditables, elements with click handlers or cursor:pointer) receive a 1-based indexed Ref-ID.
- [ ] Ref-IDs are registered in an in-memory `window.__chrome_bridge_refs` map associating numbers to DOM `WeakRef` nodes.
- [ ] Serializer formats interactive and structural elements into a clean, compact indented outline.
- [ ] Background worker handles `get_page_content` action with `compact: true` returning the semantic snapshot string.
- [ ] Snapshot generation executes in <25ms on standard web pages (e.g. Wikipedia, GitHub, Hacker News) and achieves 99%+ token reduction compared to raw HTML.
