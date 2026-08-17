# Research 03: Synchronous Chrome Python SDK API Surface

**Ticket**: `03-chrome-python-sdk-api-surface.md`  
**Status**: Completed  
**Domain**: Python SDK, API Design, DOM Manipulation, Tab Automation  

---

## 1. Executive Summary

The **Chrome SDK (`chrome`)** is a synchronous, high-ergonomics Python standard library pre-injected into every REPL session. It allows AI drivers to interact with Google Chrome cleanly without writing raw JSON-RPC queries or fighting asynchronous event loops.

Key architectural pillars:
1. **Unified Polymorphic Locators**: Methods accept integer Ref-IDs (`1`), token strings (`"[#1]"` or `"#1"`), or standard CSS selectors (`"button.submit"`).
2. **Explicit Snapshotting & Lightweight Action Acknowledgment**: Actions return small status dicts (`{"status": "ok", "action": "click", "target": "[#1]"}`), avoiding token waste in batch loops. Inspecting the page is done explicitly via `chrome.snapshot()`.
3. **Hybrid Global & Object-Oriented Tab Model**: Top-level `chrome` methods dispatch to the active tab, while `chrome.tab(id)` or `chrome.tabs` provides scoped `Tab` handles for multi-tab automation.
4. **Deterministic Waiting & Synchronization**: Built-in helpers `chrome.wait_for(target)` and `chrome.wait_for_url(pattern)` ensure reliable execution during async page transitions.

---

## 2. Polymorphic Locator Resolution Specification

When a target is passed to an interaction method (`click`, `type`, `hover`, etc.), the SDK normalizes the locator before dispatching to the native host bridge:

```python
from typing import Union

TargetLocator = Union[int, str]


def normalize_locator(target: TargetLocator) -> dict:
  """Normalize integer, Ref-ID string, or CSS selector into an IPC target payload."""
  if isinstance(target, int):
    return {"type": "ref", "refId": target}

  target_str = target.strip()

  # Matches [#12] or #12 or ref:12
  if target_str.startswith("[#") and target_str.endswith("]"):
    ref_num = int(target_str[2:-1])
    return {"type": "ref", "refId": ref_num}
  if target_str.startswith("#") and target_str[1:].isdigit():
    return {"type": "ref", "refId": int(target_str[1:])}
  if target_str.startswith("ref:") and target_str[4:].isdigit():
    return {"type": "ref", "refId": int(target_str[4:])}

  # Fallback to CSS selector
  return {"type": "css", "selector": target_str}
```

---

## 3. Class Design & Full API Surface

### 3.1 Tab Handle Class (`Tab`)

```python
class Tab:
  """Scoped browser tab handle."""

  def __init__(self, tab_id: int, client: "ChromeSocketClient"):
    self.id = tab_id
    self._client = client

  @property
  def info(self) -> dict:
    """Fetch live metadata (url, title, active status) for this tab."""
    return self._client.call("get_tab", {"tabId": self.id})

  def activate(self) -> dict:
    """Focus and switch to this tab."""
    return self._client.call("switch_tab", {"tabId": self.id})

  def close(self) -> dict:
    """Close this tab."""
    return self._client.call("close_tab", {"tabId": self.id})

  def navigate(self, url: str, timeout: float = 30.0) -> dict:
    """Navigate tab to a URL."""
    return self._client.call(
        "navigate", {"url": url, "tabId": self.id}, timeout=timeout
    )

  def reload(self, bypass_cache: bool = False) -> dict:
    """Reload the tab."""
    return self._client.call(
        "reload", {"tabId": self.id, "bypassCache": bypass_cache}
    )

  def back(self) -> dict:
    """Navigate back in history."""
    return self._client.call("go_back", {"tabId": self.id})

  def forward(self) -> dict:
    """Navigate forward in history."""
    return self._client.call("go_forward", {"tabId": self.id})

  def snapshot(self, compact: bool = True) -> str:
    """Generate a token-optimized Semantic DOM Snapshot with Ref-IDs."""
    res = self._client.call(
        "get_page_content", {"tabId": self.id, "compact": compact}
    )
    return res.get("snapshot", "")

  def click(
      self, target: TargetLocator, button: str = "left", count: int = 1
  ) -> dict:
    """Click an element by Ref-ID or CSS selector."""
    loc = normalize_locator(target)
    return self._client.call(
        "click", {"target": loc, "button": button, "count": count, "tabId": self.id}
    )

  def type(
      self,
      target: TargetLocator,
      text: str,
      clear: bool = True,
      press_enter: bool = False,
  ) -> dict:
    """Type text into an input or contenteditable element."""
    loc = normalize_locator(target)
    return self._client.call(
        "type",
        {
            "target": loc,
            "text": text,
            "clear": clear,
            "pressEnter": press_enter,
            "tabId": self.id,
        },
    )

  def press_key(self, key: str) -> dict:
    """Press a key (e.g. 'Enter', 'Tab', 'Escape', 'ArrowDown')."""
    return self._client.call("press_key", {"key": key, "tabId": self.id})

  def select(self, target: TargetLocator, value: str) -> dict:
    """Select option in a dropdown by value or text."""
    loc = normalize_locator(target)
    return self._client.call(
        "select_option", {"target": loc, "value": value, "tabId": self.id}
    )

  def hover(self, target: TargetLocator) -> dict:
    """Hover mouse over an element."""
    loc = normalize_locator(target)
    return self._client.call("hover", {"target": loc, "tabId": self.id})

  def scroll(
      self, x: int = 0, y: int = 500, target: TargetLocator = None
  ) -> dict:
    """Scroll the page or a specific container."""
    loc = normalize_locator(target) if target is not None else None
    return self._client.call(
        "scroll", {"x": x, "y": y, "target": loc, "tabId": self.id}
    )

  def get_text(self, target: TargetLocator) -> str:
    """Get inner text of an element."""
    loc = normalize_locator(target)
    res = self._client.call("get_text", {"target": loc, "tabId": self.id})
    return res.get("text", "")

  def get_attribute(self, target: TargetLocator, name: str) -> str | None:
    """Get DOM attribute value."""
    loc = normalize_locator(target)
    res = self._client.call(
        "get_attribute", {"target": loc, "name": name, "tabId": self.id}
    )
    return res.get("value")

  def eval_js(self, script: str, target: TargetLocator = None) -> Any:
    """Execute JavaScript in the page context."""
    loc = normalize_locator(target) if target is not None else None
    res = self._client.call(
        "execute_script", {"code": script, "target": loc, "tabId": self.id}
    )
    return res.get("result")

  def screenshot(self, path: str = None) -> str:
    """Capture page screenshot (returns base64 or saves to path)."""
    res = self._client.call("screenshot", {"path": path, "tabId": self.id})
    return res.get("data", "")

  def wait_for(
      self,
      target: TargetLocator,
      timeout: float = 10.0,
      state: str = "visible",
  ) -> bool:
    """Synchronously wait for an element to reach the desired state ('visible', 'hidden', 'attached')."""
    loc = normalize_locator(target)
    return self._client.call(
        "wait_for",
        {"target": loc, "state": state, "tabId": self.id},
        timeout=timeout + 2.0,
    )

  def wait_for_url(self, pattern: str, timeout: float = 15.0) -> bool:
    """Synchronously wait for current URL to match regex or substring pattern."""
    return self._client.call(
        "wait_for_url",
        {"pattern": pattern, "tabId": self.id},
        timeout=timeout + 2.0,
    )
```

---

### 3.2 Global `ChromeSDK` Top-Level Singleton

```python
class ChromeSDK:
  """Primary synchronous entrypoint injected into the REPL."""

  def __init__(self, client: ChromeSocketClient):
    self._client = client

  @property
  def tabs(self) -> list[Tab]:
    """List all open tabs as Tab handles."""
    raw_tabs = self._client.call("list_tabs")
    return [Tab(t["id"], self._client) for t in raw_tabs]

  def list_tabs(self) -> list[dict]:
    """List summary dicts for all open tabs."""
    return self._client.call("list_tabs")

  def tab(self, tab_id: int) -> Tab:
    """Get a scoped Tab handle by ID."""
    return Tab(tab_id, self._client)

  def active_tab(self) -> Tab:
    """Get Tab handle for currently active tab."""
    active = self._client.call("get_active_tab")
    return Tab(active["id"], self._client)

  def new_tab(self, url: str = "about:blank") -> Tab:
    """Open a new tab and return its Tab handle."""
    res = self._client.call("new_tab", {"url": url})
    return Tab(res["id"], self._client)

  def switch_tab(self, tab_id: int) -> dict:
    """Focus tab by ID."""
    return self._client.call("switch_tab", {"tabId": tab_id})

  def close_tab(self, tab_id: int = None) -> dict:
    """Close tab by ID or active tab."""
    return self._client.call("close_tab", {"tabId": tab_id})

  # --- Delegated Active Tab Methods ---
  def navigate(self, url: str, timeout: float = 30.0) -> dict:
    return self.active_tab().navigate(url, timeout=timeout)

  def reload(self, bypass_cache: bool = False) -> dict:
    return self.active_tab().reload(bypass_cache=bypass_cache)

  def back(self) -> dict:
    return self.active_tab().back()

  def forward(self) -> dict:
    return self.active_tab().forward()

  def snapshot(self, compact: bool = True) -> str:
    return self.active_tab().snapshot(compact=compact)

  def click(
      self, target: TargetLocator, button: str = "left", count: int = 1
  ) -> dict:
    return self.active_tab().click(target, button=button, count=count)

  def type(
      self,
      target: TargetLocator,
      text: str,
      clear: bool = True,
      press_enter: bool = False,
  ) -> dict:
    return self.active_tab().type(
        target, text, clear=clear, press_enter=press_enter
    )

  def press_key(self, key: str) -> dict:
    return self.active_tab().press_key(key)

  def select(self, target: TargetLocator, value: str) -> dict:
    return self.active_tab().select(target, value)

  def hover(self, target: TargetLocator) -> dict:
    return self.active_tab().hover(target)

  def scroll(
      self, x: int = 0, y: int = 500, target: TargetLocator = None
  ) -> dict:
    return self.active_tab().scroll(x, y, target)

  def get_text(self, target: TargetLocator) -> str:
    return self.active_tab().get_text(target)

  def get_attribute(self, target: TargetLocator, name: str) -> str | None:
    return self.active_tab().get_attribute(target, name)

  def eval_js(self, script: str, target: TargetLocator = None) -> Any:
    return self.active_tab().eval_js(script, target)

  def screenshot(self, path: str = None) -> str:
    return self.active_tab().screenshot(path)

  def wait_for(
      self,
      target: TargetLocator,
      timeout: float = 10.0,
      state: str = "visible",
  ) -> bool:
    return self.active_tab().wait_for(target, timeout=timeout, state=state)

  def wait_for_url(self, pattern: str, timeout: float = 15.0) -> bool:
    return self.active_tab().wait_for_url(pattern, timeout=timeout)
```

---

## 4. Error Hierarchy

```python
class ChromeBridgeError(Exception):
  """Base exception for all Chrome Bridge operations."""

  pass


class ElementNotFoundError(ChromeBridgeError):
  """Raised when a Ref-ID or CSS selector cannot be located."""

  def __init__(self, target: TargetLocator, tab_id: int, snapshot_hint: str = ""):
    super().__init__(
        f"Element matching '{target}' not found in tab {tab_id}. "
        f"The DOM may have changed since the last snapshot. {snapshot_hint}"
    )


class NavigationTimeoutError(ChromeBridgeError):
  """Raised when page load or navigation exceeds timeout."""

  pass
```
