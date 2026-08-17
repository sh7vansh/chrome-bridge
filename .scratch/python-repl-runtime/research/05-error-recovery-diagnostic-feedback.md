# Research 05: Error Recovery & Diagnostic Feedback Specification

**Ticket**: `05-error-recovery-diagnostic-feedback.md`  
**Status**: Completed  
**Type**: Grilling / HITL  
**Domain**: Diagnostics, Error Recovery, Self-Healing, Python REPL Runtime, Browser Automation  

---

## 1. Executive Summary

Browser automation failures in LLM agent workflows typically cost multiple round-trips:
1. Turn 1: Agent issues `chrome.click("[#14]")`.
2. Turn 2: Extension returns generic `Element not found`. Agent spends a turn asking `chrome.snapshot()`.
3. Turn 3: Extension returns new snapshot. Agent analyzes new Ref-ID `[#18]` and issues `chrome.click("[#18]")`.

This specification establishes a **Single-Turn Self-Healing Diagnostic Architecture**:
- **Diagnostic Auto-Snapshot**: When an action raises an exception, the runtime automatically attaches a fresh, compact Semantic DOM Snapshot into the exception payload.
- **Fuzzy Near-Match Heuristics**: If a Ref-ID has mutated due to SPA re-rendering, the extension computes the top candidate elements matching the historical tag, role, and accessible name.
- **Action Interceptor Inspection**: When pointer events are intercepted (e.g. by cookie banners or modal backdrops), the runtime identifies the exact intercepting element and Ref-ID.
- **Rich Timeout Introspection**: Timeouts distinguish between elements that never loaded vs. elements present in the DOM but hidden via CSS (`display: none`, `opacity: 0`).

---

## 2. Python Exception Hierarchy & Structured Attributes

All exceptions derive from `ChromeBridgeError` and carry structured metadata for runtime serialization:

```python
class ChromeBridgeError(Exception):
  """Base exception for all Chrome Bridge operations."""

  def __init__(self, message: str, tab_id: Optional[int] = None):
    super().__init__(message)
    self.tab_id = tab_id
    self.auto_snapshot: Optional[str] = None


class ElementNotFoundError(ChromeBridgeError):
  """Raised when a Ref-ID or CSS selector cannot be located."""

  def __init__(
      self,
      target: str,
      tab_id: int,
      stale: bool = False,
      suggestions: Optional[List[Dict[str, Any]]] = None,
      url: str = "",
  ):
    msg = f"Element matching '{target}' not found in tab {tab_id} (URL: {url})."
    if stale:
      msg += " The DOM mutated since the last snapshot was generated."
    if suggestions:
      sug_str = ", ".join(
          f"[{s['ref']}] ({s['role']} '{s['name']}')" for s in suggestions
      )
      msg += f" Did you mean: {sug_str}?"

    super().__init__(msg, tab_id)
    self.target = target
    self.stale = stale
    self.suggestions = suggestions or []


class ActionInterceptionError(ChromeBridgeError):
  """Raised when coordinate hit-testing is intercepted by an overlapping element."""

  def __init__(
      self,
      target: str,
      interceptor_tag: str,
      interceptor_ref: Optional[str],
      interceptor_desc: str,
      tab_id: int,
  ):
    interceptor_label = (
        f"[{interceptor_ref}] ({interceptor_desc})"
        if interceptor_ref
        else f"<{interceptor_tag}> ({interceptor_desc})"
    )
    msg = (
        f"Click on target '{target}' was intercepted by overlapping element"
        f" {interceptor_label} in tab {tab_id}. Dismiss or close the overlay"
        " before interacting with the target."
    )
    super().__init__(msg, tab_id)
    self.target = target
    self.interceptor_tag = interceptor_tag
    self.interceptor_ref = interceptor_ref


class NavigationTimeoutError(ChromeBridgeError):
  """Raised when navigation or element condition waiting exceeds deadline."""

  def __init__(
      self,
      target: Optional[str],
      timeout: float,
      url: str,
      ready_state: str,
      dom_state: str,
      tab_id: int,
  ):
    msg = (
        f"Timed out after {timeout:.1f}s waiting for '{target or url}' in tab"
        f" {tab_id}."
    )
    msg += f" (Current URL: {url}, readyState: '{ready_state}', DOM state:"
    f" '{dom_state}')"
    super().__init__(msg, tab_id)
    self.timeout = timeout
    self.url = url
    self.ready_state = ready_state
    self.dom_state = dom_state
```

---

## 3. Diagnostic Auto-Snapshot Injection Protocol

When a script throws an unhandled `ChromeBridgeError`:
1. The REPL catches the exception.
2. The runtime invokes `tab.snapshot(compact=True)` synchronously.
3. The snapshot is formatted under the `[diagnostic_auto_snapshot]` block directly in the tool result:

```text
[error]
ElementNotFoundError: Element matching '[#14]' not found in tab 1 (URL: https://store.example.com/cart). The DOM mutated since the last snapshot was generated. Did you mean: [#18] (button 'Checkout')?

[diagnostic_auto_snapshot]
[#1] Header: 'Acme Store'
[#2] Navigation: 'Shop' | 'Deals' | 'Cart (2)'
[#18] Button: 'Checkout' [enabled]
[#19] Button: 'Continue Shopping'

[stderr]
Traceback (most recent call last):
  File "<repl>", line 3, in <module>
    chrome.click("[#14]")
  File "chrome_sdk.py", line 112, in click
    raise ElementNotFoundError(target, self.id, stale=True, suggestions=[{'ref': '#18', 'role': 'button', 'name': 'Checkout'}])
```

---

## 4. Stale Ref-ID Tracking & Fuzzy Near-Match Algorithm

The extension maintains an in-memory page snapshot history in `window.__chrome_bridge_history`:
1. When generating snapshot $S_k$, map `refId -> { tag, role, name, classes, path }`.
2. When an action targets `refId = 14` during state $S_{k+1}$, and `14` is not found in the live map:
   - Mark `stale = true`.
   - Retrieve historical metadata for `14` (e.g. `role: "button"`, `name: "Checkout"`).
   - Compute similarity score across all live registered nodes in $S_{k+1}$:
     $$\text{Score} = w_{\text{role}} \cdot \mathbb{I}(\text{role match}) + w_{\text{name}} \cdot \text{NormalizedLevenshtein}(\text{name}_1, \text{name}_2) + w_{\text{tag}} \cdot \mathbb{I}(\text{tag match})$$
   - Pick top candidates with $\text{Score} \ge 0.75$.
   - Format suggestions into the error response.

---

## 5. Action Interception Detection & Auto-Scroll

Before calculating coordinates for a pointer event (`click`, `hover`):
1. **Auto-Scroll**:
   ```javascript
   targetElement.scrollIntoView({
     behavior: 'instant',
     block: 'center',
     inline: 'center',
   });
```
2. **Hit Testing**:
   - Compute bounding client rectangle center $(c_x, c_y)$.
   - Query `const hit = document.elementFromPoint(cx, cy);`.
   - Check if `targetElement.contains(hit)` is `true`.
   - If `false`, inspect `hit`:
     - Search upward for closest modal dialog, banner, overlay, or fixed header (`hit.closest('dialog, [role="dialog"], header, .modal, .overlay, [aria-modal="true"]')`).
     - Retrieve or generate a Ref-ID for the interceptor node.
     - Return `ACTION_INTERCEPTED` IPC response with interceptor metadata.

---

## 6. Timeout & Navigation Diagnostics

When `chrome.wait_for(target, timeout)` expires:
1. Query `document.readyState` (`loading`, `interactive`, `complete`).
2. Query `window.location.href`.
3. Check DOM presence:
   - If selector/ref exists in DOM:
     - Check `style.display === 'none'` or `computedStyle.visibility === 'hidden'` $\rightarrow$ `DOM state: 'hidden in DOM'`.
     - Check `computedStyle.opacity === '0'` $\rightarrow$ `DOM state: 'zero opacity'`.
     - Check dimensions $\rightarrow$ `DOM state: 'zero width/height'`.
   - If not found in DOM $\rightarrow$ `DOM state: 'absent from DOM'`.
4. Construct descriptive `NavigationTimeoutError` with actionable diagnosis.
