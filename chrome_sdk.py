r"""Synchronous Python SDK and IPC Client for Chrome Bridge.

Persistent Python REPL Runtime for AI Browser Automation.

Standard Composition Lifecycle:
===============================
1. Orientation:
   >>> from chrome_sdk import chrome
   >>> snapshot = chrome.snapshot()
   >>> print(snapshot)
   # Inspect the returned Semantic DOM outline to discover element Ref-IDs:
   # [#1] <input type="text" placeholder="Search Google">
   # [#2] <button type="submit">Google Search</button>

2. Targeted Actions:
   # Interact using Ref-IDs, integer tokens, or CSS selectors
   >>> chrome.type("[#1]", "Claude Sonnet", press_enter=True)

3. Synchronization:
   # Wait for URL transition or dynamic element appearance
   >>> chrome.wait_for_url(r"search\?q=")
   >>> chrome.wait_for("[#search-results]", timeout=10.0)

4. Extraction & Subroutines:
   # Extract text or run JavaScript in page context
   >>> titles = chrome.eval_js('''
   ...     Array.from(document.querySelectorAll('h3')).map(e => e.innerText)
   ... ''')
   >>> print("Extracted Titles:", titles)

5. Fast Media Control (Zero-DOM):
   >>> status = chrome.media.status()
   >>> chrome.media.toggle()
"""

import os
import sys
import time
from typing import Any, Dict, List, Optional, Set, Union

# Ensure UTF-8 streams cross-platform (especially on Windows)
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def resolve_runtime_directory() -> str:
    """Resolve the active Chrome Bridge runtime directory across standard candidate locations."""
    cwd = os.getcwd()
    file_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else None

    candidates: List[str] = [
        cwd,
        os.path.expanduser("~/.chrome-bridge"),
        os.path.expanduser("~/chrome-bridge"),
    ]
    if file_dir and file_dir not in candidates:
        candidates.append(file_dir)

    for c in candidates:
        if os.path.exists(os.path.join(c, "chrome_sdk.py")):
            return os.path.abspath(c)
    return os.path.abspath(os.path.expanduser("~/.chrome-bridge"))


def auto_bootstrap_environment(target_dir: Optional[str] = None) -> List[str]:
    """Auto-discover and attach runtime directories and .venv site-packages to sys.path.

    Returns list of site-packages paths attached.
    """
    import glob
    import site

    added_paths: List[str] = []
    base_dir = os.path.abspath(target_dir) if target_dir else resolve_runtime_directory()

    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    venv_dir = os.path.join(base_dir, ".venv")
    if os.path.isdir(venv_dir):
        if sys.platform == "win32":
            sp = os.path.join(venv_dir, "Lib", "site-packages")
            if os.path.isdir(sp) and sp not in sys.path:
                site.addsitedir(sp)
                added_paths.append(sp)
        else:
            for sp in glob.glob(os.path.join(venv_dir, "lib", "python*", "site-packages")):
                if os.path.isdir(sp) and sp not in sys.path:
                    site.addsitedir(sp)
                    added_paths.append(sp)

    return added_paths


# Automatically bootstrap runtime environment and site-packages on import
auto_bootstrap_environment()

# Import modular subsystems from chrome_bridge
from chrome_bridge.exceptions import (
    CRITICAL_DELETION_REGEX,
    CRITICAL_DELETION_TERMS,
    DEFAULT_BROWSER_UNAVAILABLE_MSG,
    DEFAULT_PORT_FILE,
    DEFAULT_SOCKET_PATH,
    SOCKET_PATH,
    SSO_ALLOWLIST,
    ActionInterceptionError,
    BrowserUnavailableError,
    ChromeBridgeError,
    ElementNotFoundError,
    NavigationTimeoutError,
    RunawayLoopDetectedError,
    SecurityException,
    TargetLocator,
    _extract_hostname,
    _format_ref_id,
    normalize_locator,
)
from chrome_bridge.security import (
    ActionTracker,
    ChromeBridgeWorkerTelemetry,
    SafetyController,
    SecurityGateway,
    defang_telemetry_payload,
    global_safety,
    wrap_untrusted_data,
)
from chrome_bridge.transport import (
    ChromeSocketClient,
    TransportClient,
)
from chrome_bridge.compiler import (
    DomBatchSynthesizer,
    DomCompiler,
    _DISCOVERY_HELPER_JS,
)


class TabMedia:
    """Fast-path media controller attached to a Tab instance.

    Provides zero-DOM-overhead media control for HTML5 <video> / <audio> elements
    and the browser MediaSession API. Directly penetrates open shadow roots (e.g.
    YouTube, Spotify, Netflix web players) without generating expensive DOM snapshots.

    Example:
        >>> # Check playback state and metadata
        >>> print(chrome.media.status())
        >>> 
        >>> # Toggle play/pause
        >>> chrome.media.toggle()
        >>> 
        >>> # Relative seek (+15s forward or -10s backward)
        >>> chrome.media.seek(15.0)
        >>> 
        >>> # Set volume level
        >>> chrome.media.set_volume(0.8)
    """

    _FIND_MEDIA_JS = """
    function findMediaElement(root = document) {
        let el = root.querySelector('video, audio');
        if (el) return el;
        const all = root.querySelectorAll('*');
        for (const node of all) {
            if (node.shadowRoot) {
                const nested = findMediaElement(node.shadowRoot);
                if (nested) return nested;
            }
        }
        return null;
    }
    """

    def __init__(self, tab: Any):
        self._tab = tab

    def status(self) -> Dict[str, Any]:
        """Fetch real-time media player state via HTML5 Video/Audio & MediaSession APIs."""
        js = DomCompiler.compile_media_control("status")
        return self._tab.eval_js(js) or {}

    def toggle(self) -> Dict[str, Any]:
        """Toggle play/pause on the active media element."""
        js = DomCompiler.compile_media_control("toggle")
        return self._tab.eval_js(js) or {}

    def play(self) -> Dict[str, Any]:
        """Resume playback on the active media element."""
        js = DomCompiler.compile_media_control("play")
        return self._tab.eval_js(js) or {}

    def pause(self) -> Dict[str, Any]:
        """Pause playback on the active media element."""
        js = DomCompiler.compile_media_control("pause")
        return self._tab.eval_js(js) or {}

    def seek(self, seconds: float) -> Dict[str, Any]:
        """Seek relative (+/- seconds) or step playback time."""
        js = DomCompiler.compile_media_control("seek", seconds=seconds)
        return self._tab.eval_js(js) or {}

    def set_volume(self, volume: float) -> Dict[str, Any]:
        """Set media volume level between 0.0 (muted) and 1.0 (max)."""
        js = DomCompiler.compile_media_control("set_volume", volume=volume)
        return self._tab.eval_js(js) or {}


class ElementHandle:
    """Handle to a resolved DOM element allowing fluent chained interactions.

    Provides chained methods (.click(), .type(), .select(), .hover())
    with built-in dynamic micro-waits for closed-loop execution without prior snapshots.

    Example:
        >>> chrome.find_input("Email").type("alice@example.com")
        >>> chrome.find_button("Sign In").click()
        >>> chrome.find_text("Dashboard").hover()
    """

    def __init__(
        self,
        tab: "Tab",
        target: TargetLocator,
        tag_name: str = "",
        role: str = "",
        text: str = "",
        attributes: Optional[Dict[str, Any]] = None,
    ):
        self._tab = tab
        self.target = target
        self._tag_name = tag_name
        self._role = role
        self._cached_text = text
        self._attributes = attributes or {}

    def __repr__(self) -> str:
        target_repr = str(self.target)
        role_repr = f" role='{self._role}'" if self._role else ""
        text_repr = f" text='{self._cached_text[:30]}'" if self._cached_text else ""
        return f"<ElementHandle target={target_repr}{role_repr}{text_repr}>"

    @property
    def tab(self) -> "Tab":
        """Tab instance this element belongs to."""
        return self._tab

    @property
    def locator(self) -> TargetLocator:
        """Target locator for this element."""
        return self.target

    @property
    def tag_name(self) -> str:
        """HTML tag name of this element (e.g. 'button', 'input', 'select')."""
        return self._tag_name

    @property
    def role(self) -> str:
        """Accessibility or ARIA role of this element (e.g. 'button', 'radio', 'combobox')."""
        return self._role

    @property
    def is_radio(self) -> bool:
        """True if the element represents a radio button."""
        if self._role == "radio":
            return True
        if self._tag_name and self._tag_name.lower() not in ("input", ""):
            return False
        if hasattr(self, "eval_js"):
            try:
                res = self.eval_js("((this.tagName === 'INPUT' && this.type === 'radio') || this.getAttribute('role') === 'radio')")
                if isinstance(res, bool):
                    return res
                if isinstance(res, dict) and "result" in res and isinstance(res["result"], bool):
                    return res["result"]
            except Exception:
                pass
        return False

    @property
    def text(self) -> str:
        """Extract live text content of the element."""
        return self._tab.get_text(self.target, wrap=False)

    def click(self, button: str = "left", count: int = 1, safety_check: bool = True) -> "ElementHandle":
        """Click the element. Returns self for chaining."""
        self._tab.click(self.target, button=button, count=count, safety_check=safety_check)
        return self

    def type(
        self,
        text: str,
        clear: bool = False,
        press_enter: bool = False,
        safety_check: bool = True,
    ) -> "ElementHandle":
        """Type text into the element. Returns self for chaining."""
        self._tab.type(self.target, text=text, clear=clear, press_enter=press_enter, safety_check=safety_check)
        return self

    def select(self, value: str, safety_check: bool = True) -> "ElementHandle":
        """Select option in a <select> dropdown. Returns self for chaining."""
        self._tab.select(self.target, value=value, safety_check=safety_check)
        return self

    def hover(self) -> "ElementHandle":
        """Hover mouse over the element. Returns self for chaining."""
        self._tab.hover(self.target)
        return self

    def scroll_into_view(self) -> "ElementHandle":
        """Scroll the element into viewport view. Returns self for chaining."""
        self.eval_js("this.scrollIntoView({behavior: 'instant', block: 'center', inline: 'center'})")
        return self

    def get_attribute(self, name: str) -> Optional[str]:
        """Retrieve element DOM attribute."""
        return self._tab.get_attribute(self.target, name)

    def eval_js(self, script: str) -> Any:
        """Execute JavaScript with `this` bound to this element."""
        return self._tab.eval_js(script, target=self.target)


class Tab:
    """Scoped browser tab handle and procedural action context.

    Provides high-level DOM interactions, Ref-ID resolution, navigation,
    and media fast-paths scoped to a single browser tab.

    Example Workflow:
        >>> tab = chrome.active_tab
        >>> print(tab.snapshot())
        >>> tab.type("[#search_bar]", "Documentation", press_enter=True)
        >>> tab.wait_for_url(r"/docs")
        >>> data = tab.get_text("[#content]")
    """

    def __init__(
        self,
        tab_id: Optional[int] = None,
        client: Optional[TransportClient] = None,
        title: str = "",
        url: str = "",
        active: bool = False,
    ):
        self.id = tab_id
        self._client = client or ChromeSocketClient()
        self.title = title
        self.url = url
        self.active = active
        self._media_controller: Optional[TabMedia] = None
        self.allowed_origins: Set[str] = set()
        if self.url:
            host = _extract_hostname(self.url)
            if host:
                self.allowed_origins.add(host)
        self.safety = global_safety

    def __repr__(self) -> str:
        tab_id_repr = self.id if self.id is not None else "active"
        return f'<Tab id={tab_id_repr} title="{self.title}" url="{self.url}" active={self.active}>'

    @property
    def origin(self) -> str:
        if self.url:
            import urllib.parse
            parsed = urllib.parse.urlparse(self.url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
            if parsed.netloc:
                return parsed.netloc
            if not parsed.scheme and "/" not in self.url:
                return self.url
        return ""

    @property
    def info(self) -> Dict[str, Any]:
        """Fetch live metadata (url, title, active status) for this tab."""
        tabs = self._client.call("list_tabs")
        for t in tabs:
            if self.id is not None and t.get("id") == self.id:
                self.title = t.get("title", "")
                self.url = t.get("url", "")
                self.active = t.get("active", False)
                return t
            elif self.id is None and t.get("active", False):
                self.title = t.get("title", "")
                self.url = t.get("url", "")
                self.active = True
                return t
        return {"id": self.id, "title": self.title, "url": self.url, "active": self.active}

    @property
    def media(self) -> TabMedia:
        """Fast-path media controller for HTML5 audio/video and MediaSession APIs."""
        if self._media_controller is None:
            self._media_controller = TabMedia(self)
        return self._media_controller

    def _safety_check_action(
        self,
        action: str,
        target: Any = None,
        text: str = "",
        safety_check: bool = True,
    ) -> None:
        """Verify action against SecurityGateway Layer 2 and Layer 5."""
        self.safety.verify_action(
            action=action,
            target=target,
            url=self.url,
            tab_id=self.id,
            text=text,
            safety_check=safety_check,
        )

    def activate(self) -> Dict[str, Any]:
        """Focus and switch to this tab."""
        return self._client.call("switch_tab", {"tabId": self.id})

    def close(self) -> Dict[str, Any]:
        """Safely closes the tab."""
        try:
            tabs = self._client.call("list_tabs")
            if isinstance(tabs, list) and len(tabs) <= 1:
                self._client.call("navigate", {"url": "about:blank", "newTab": True})
            return self._client.call("close_tab", {"tabId": self.id})
        except Exception:
            return self._client.call("close_tab", {"tabId": self.id})

    def navigate(self, url: str, timeout: float = 30.0, safety_check: bool = True) -> Dict[str, Any]:
        """Navigates the tab to the specified URL while enforcing origin locking."""
        self.safety.verify_navigation(
            url=url,
            current_url=self.url,
            tab_origins=self.allowed_origins,
            tab_id=self.id,
            safety_check=safety_check,
        )

        try:
            self.eval_js("""
                window.onbeforeunload = null;
                window.addEventListener('beforeunload', (e) => {
                    e.stopImmediatePropagation();
                }, true);
            """)
        except Exception:
            pass

        res = self._client.call("navigate", {"url": url, "tabId": self.id}, timeout=timeout)
        self.url = res.get("url", url) if isinstance(res, dict) else url
        target_host = _extract_hostname(url)
        if target_host:
            self.allowed_origins.add(target_host)
        return res

    def reload(self, bypass_cache: bool = False) -> Dict[str, Any]:
        """Reload the tab."""
        return self._client.call("reload", {"tabId": self.id, "bypassCache": bypass_cache})

    def back(self) -> Dict[str, Any]:
        """Navigate back in history."""
        return self._client.call("go_back", {"tabId": self.id})

    def forward(self) -> Dict[str, Any]:
        """Navigate forward in history."""
        return self._client.call("go_forward", {"tabId": self.id})

    def snapshot(self, compact: bool = True, wrap: bool = True, format: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
        """Generate a token-optimized Semantic DOM Snapshot with Ref-IDs."""
        is_compact = (format == "compact") if format is not None else compact
        res = self._client.call("get_page_content", {"tabId": self.id, "compact": is_compact})
        raw = res.get("snapshot", "") if isinstance(res, dict) else str(res)
        if wrap:
            return self.safety.sanitize_inbound(raw, origin=self.origin, selector="document")
        return raw

    def click(
        self,
        target: TargetLocator,
        button: str = "left",
        count: int = 1,
        safety_check: bool = True,
    ) -> Dict[str, Any]:
        """Click an element identified by Ref-ID or CSS selector."""
        self._safety_check_action("click", target, safety_check=safety_check)
        loc = normalize_locator(target)
        return self._client.call(
            "click",
            {"target": loc, "button": button, "count": count, "tabId": self.id},
            timeout=15.0,
        )

    def type(
        self,
        target: TargetLocator,
        text: str,
        clear: bool = True,
        press_enter: bool = False,
        safety_check: bool = True,
    ) -> Dict[str, Any]:
        """Type text into an input, textarea, or contenteditable element."""
        self._safety_check_action("type", target, text=text, safety_check=safety_check)
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
            timeout=15.0,
        )

    def press_key(self, key: str, safety_check: bool = True) -> Dict[str, Any]:
        """Press a keyboard key (e.g., 'Enter', 'Tab', 'Escape', 'ArrowDown')."""
        self._safety_check_action("press_key", key, safety_check=safety_check)
        return self._client.call("press_key", {"key": key, "tabId": self.id})

    def select(self, target: TargetLocator, value: str, safety_check: bool = True) -> Dict[str, Any]:
        """Select an option in a <select> dropdown by value or label."""
        self._safety_check_action("select", target, text=value, safety_check=safety_check)
        loc = normalize_locator(target)
        return self._client.call("select_option", {"target": loc, "value": value, "tabId": self.id})

    def hover(self, target: TargetLocator) -> Dict[str, Any]:
        """Hover mouse pointer over an element to trigger tooltips or dropdown menus."""
        loc = normalize_locator(target)
        return self._client.call("hover", {"target": loc, "tabId": self.id})

    def scroll(self, x: int = 0, y: int = 500, target: Optional[TargetLocator] = None) -> Dict[str, Any]:
        """Scroll the window or a specific scrollable container."""
        self._safety_check_action("scroll", target)
        loc = normalize_locator(target) if target is not None else None
        return self._client.call("scroll", {"x": x, "y": y, "target": loc, "tabId": self.id})

    def get_text(self, target: TargetLocator, wrap: bool = True) -> str:
        """Extract inner text content of an element."""
        loc = normalize_locator(target)
        res = self._client.call("get_text", {"target": loc, "tabId": self.id})
        raw = res.get("text", "") if isinstance(res, dict) else str(res)
        if wrap:
            return self.safety.sanitize_inbound(raw, origin=self.origin, selector=str(target))
        return raw

    def get_attribute(self, target: TargetLocator, name: str) -> Optional[str]:
        """Retrieve the value of an element DOM attribute."""
        loc = normalize_locator(target)
        res = self._client.call("get_attribute", {"target": loc, "name": name, "tabId": self.id})
        return res.get("value") if isinstance(res, dict) else None

    def eval_js(self, script: str, target: Optional[TargetLocator] = None) -> Any:
        """Execute JavaScript directly in the active tab context."""
        loc = normalize_locator(target) if target is not None else None
        return self._client.call("execute_script", {"code": script, "target": loc, "tabId": self.id})

    def screenshot(self, path: Optional[str] = None) -> str:
        """Capture a page screenshot."""
        res = self._client.call("screenshot", {"path": path, "tabId": self.id})
        return res.get("dataUrl") or res.get("data", "")

    def wait_for(self, target: TargetLocator, timeout: float = 10.0, state: str = "visible") -> bool:
        """Synchronously wait for an element to reach a target lifecycle state."""
        loc = normalize_locator(target)
        return self._client.call(
            "wait_for",
            {"target": loc, "state": state, "timeout": timeout, "tabId": self.id},
            timeout=timeout + 3.0,
        )

    def wait_for_url(self, pattern: str, timeout: float = 15.0) -> bool:
        r"""Synchronously wait for current URL to match a regex pattern."""
        return self._client.call(
            "wait_for_url",
            {"pattern": pattern, "timeout": timeout, "tabId": self.id},
            timeout=timeout + 3.0,
        )

    def help(self) -> str:
        """Return a formatted quick reference of available SDK methods and examples."""
        return (
            "Chrome Bridge SDK Quick Reference:\n"
            "==================================\n"
            "  DOM Orientation:\n"
            "    chrome.snapshot(compact=True)     -> Outline with [#N] Ref-IDs\n\n"
            "  Fluent In-Script Discovery (Chained Actions without prior snapshot):\n"
            "    chrome.find(target)               -> ElementHandle\n"
            "    chrome.find_text('Text')          -> .click(), .type(), .hover()\n"
            "    chrome.find_input('Placeholder')  -> .type('value', clear=True)\n"
            "    chrome.find_button('Submit')      -> .click()\n"
            "    chrome.query_all('css_selector')  -> List[ElementHandle]\n\n"
            "  Compound Batch Helpers:\n"
            "    chrome.fill_form({'Email': '...'}, submit='Sign In')\n"
            "    chrome.extract_items('article', {'title': 'h2', 'link': 'a@href'})\n"
            "    chrome.search('query', engine='google')\n\n"
            "  Element Interactions (Target: [#N], int N, or 'css_selector'):\n"
            "    chrome.click(target, button='left', count=1)\n"
            "    chrome.type(target, 'text', clear=True, press_enter=False)\n"
            "    chrome.select(target, 'value')\n"
            "    chrome.hover(target)\n"
            "    chrome.scroll(x=0, y=500, target=None)\n"
            "    chrome.press_key('Enter')\n\n"
            "  Extraction & Scripting:\n"
            "    chrome.get_text(target)           -> Inner text in untrusted tags\n"
            "    chrome.get_attribute(target, name)\n"
            "    chrome.eval_js('document.title')\n"
            "    chrome.screenshot(path=None)\n\n"
            "  Tabs & Navigation:\n"
            "    chrome.tabs, chrome.active_tab, chrome.get_tab(id), chrome.new_tab(url)\n"
            "    chrome.navigate(url), chrome.reload(), chrome.back(), chrome.forward()\n\n"
            "  Media Fast-Paths (Zero-DOM Shadow-Root Penetration):\n"
            "    chrome.media.status()             -> Player state, title, artist, time\n"
            "    chrome.media.toggle(), play(), pause()\n"
            "    chrome.media.seek(15.0), chrome.media.set_volume(0.8)\n\n"
            "  Safety & Governance:\n"
            "    chrome.safety.allow_origin('api.example.com')\n"
            "    with chrome.safety.permit_destructive(): ...\n"
        )

    def _collect_fuzzy_suggestions(self, query: str) -> List[Dict[str, Any]]:
        return DomCompiler.collect_fuzzy_suggestions(self, query)

    def _poll_find(self, finder_func, query: str, timeout: float = 1.5, interval: float = 0.1) -> ElementHandle:
        return DomCompiler.poll_find_element(
            tab=self,
            finder_func=finder_func,
            query=query,
            handle_factory=ElementHandle,
            timeout=timeout,
            interval=interval,
        )

    def find_text(self, text: str, exact: bool = False, timeout: float = 1.5) -> ElementHandle:
        """Find a visible DOM element by inner text or accessible content in a single roundtrip."""
        rpc = DomCompiler.compile_find_element_rpc(query=text, strategy="text", exact=exact, timeout=timeout)
        params = rpc.get("params", {})
        params["tabId"] = self.id
        res = self._client.call(rpc["action"], params, timeout=(timeout or 1.5) + 3.0)
        if isinstance(res, dict) and (res.get("selector") or res.get("target")):
            return ElementHandle(
                tab=self,
                target=res.get("selector") or res.get("target"),
                tag_name=res.get("tagName", ""),
                role=res.get("role", ""),
                text=res.get("text", ""),
            )
        raise ElementNotFoundError(target=text, tab_id=self.id, url=getattr(self, "url", ""))

    def find_input(self, placeholder_or_label: str, timeout: float = 1.5) -> ElementHandle:
        """Find an input, textarea, or select element by placeholder or label in a single roundtrip."""
        rpc = DomCompiler.compile_find_element_rpc(query=placeholder_or_label, strategy="input", timeout=timeout)
        params = rpc.get("params", {})
        params["tabId"] = self.id
        res = self._client.call(rpc["action"], params, timeout=(timeout or 1.5) + 3.0)
        if isinstance(res, dict) and (res.get("selector") or res.get("target")):
            return ElementHandle(
                tab=self,
                target=res.get("selector") or res.get("target"),
                tag_name=res.get("tagName", ""),
                role=res.get("role", ""),
                text=res.get("text", ""),
            )
        raise ElementNotFoundError(target=placeholder_or_label, tab_id=self.id, url=getattr(self, "url", ""))

    def find_button(self, name: str, exact: bool = False, timeout: float = 1.5) -> ElementHandle:
        """Find a button, submit input, or clickable element in a single roundtrip."""
        rpc = DomCompiler.compile_find_element_rpc(query=name, strategy="button", exact=exact, timeout=timeout)
        params = rpc.get("params", {})
        params["tabId"] = self.id
        res = self._client.call(rpc["action"], params, timeout=(timeout or 1.5) + 3.0)
        if isinstance(res, dict) and (res.get("selector") or res.get("target")):
            return ElementHandle(
                tab=self,
                target=res.get("selector") or res.get("target"),
                tag_name=res.get("tagName", ""),
                role=res.get("role", ""),
                text=res.get("text", ""),
            )
        raise ElementNotFoundError(target=name, tab_id=self.id, url=getattr(self, "url", ""))

    def query_all(self, css_selector: str) -> List[ElementHandle]:
        """Find all matching visible elements by CSS selector in a single roundtrip."""
        rpc = DomCompiler.compile_query_elements_rpc(selector=css_selector)
        params = rpc.get("params", {})
        params["tabId"] = self.id
        res = self._client.call(rpc["action"], params)
        raw_items = res if isinstance(res, list) else (res.get("result") if isinstance(res, dict) and isinstance(res.get("result"), list) else [])
        results: List[ElementHandle] = []
        if isinstance(raw_items, list):
            for item in raw_items:
                if isinstance(item, dict):
                    target = item.get("selector") or item.get("target") or item.get("ref")
                    if target is not None:
                        results.append(
                            ElementHandle(
                                tab=self,
                                target=target,
                                tag_name=item.get("tagName", ""),
                                role=item.get("role", ""),
                                text=item.get("text", ""),
                            )
                        )
        return results

    def find(self, target: Union[str, int], timeout: float = 1.5) -> ElementHandle:
        """Polymorphically find an element by Ref-ID, CSS selector, button name, input label, or text in 1 roundtrip."""
        if isinstance(target, int):
            return ElementHandle(tab=self, target=target)
        target_str = str(target).strip()
        if target_str.startswith("[#") or (target_str.startswith("#") and target_str[1:].isdigit()):
            return ElementHandle(tab=self, target=target_str)

        rpc = DomCompiler.compile_find_element_rpc(query=target_str, strategy="polymorphic", timeout=timeout)
        params = rpc.get("params", {})
        params["tabId"] = self.id
        res = self._client.call(rpc["action"], params, timeout=(timeout or 1.5) + 3.0)
        if isinstance(res, dict) and (res.get("selector") or res.get("target")):
            return ElementHandle(
                tab=self,
                target=res.get("selector") or res.get("target"),
                tag_name=res.get("tagName", ""),
                role=res.get("role", ""),
                text=res.get("text", ""),
            )
        raise ElementNotFoundError(target=target_str, tab_id=self.id, url=getattr(self, "url", ""))

    def fill_form(self, mapping: Dict[str, Any], submit: Optional[Union[str, bool]] = None) -> Dict[str, Any]:
        """Fill multiple form inputs, textareas, selects, and checkboxes in a single atomic in-page pass."""
        action_rpc = DomCompiler.compile_action_rpc("fill_form", mapping=mapping, submit=submit)
        params = action_rpc.get("params", {})
        params["tabId"] = self.id
        res = self._client.call(action_rpc["action"], params)
        if isinstance(res, dict) and res.get("errors"):
            first_err = res["errors"][0]
            field_name = first_err.get("field", "form_field")
            raise ElementNotFoundError(target=field_name, tab_id=self.id, url=self.url)
        return res if isinstance(res, dict) else {"success": True, "filled": len(mapping), "submitted": bool(submit)}

    def extract_items(self, container_selector: str, fields: Dict[str, str]) -> List[Dict[str, str]]:
        """Extract structured data rows and attributes across repeated container elements in a single JS pass."""
        js = DomCompiler.compile_extract_items_js(container_selector, fields)
        res = self.eval_js(js)
        if isinstance(res, list):
            return res
        elif isinstance(res, dict) and "result" in res and isinstance(res["result"], list):
            return res["result"]
        return []

    _SEARCH_ENGINES: Dict[str, str] = DomCompiler.SEARCH_ENGINES

    def search(self, query: str, engine: str = "google") -> Dict[str, Any]:
        """Execute search query via search engine shortcut."""
        target_url = DomCompiler.compile_search_url(query, engine=engine)
        if target_url:
            self.safety.allow_origin(target_url)
            host = _extract_hostname(target_url)
            if host:
                self.allowed_origins.add(host)

        return self.navigate(target_url)

    def get_ambient_header(self) -> str:
        """Generate standardized ambient orientation header for this tab."""
        info = self.info if hasattr(self, "info") else {}
        tid = self.id if self.id is not None else info.get("id")
        tab_id_repr = f"#{tid}" if tid is not None else "#1"
        url = info.get("url") or getattr(self, "url", "") or "about:blank"
        title = info.get("title") or getattr(self, "title", "") or "Chrome"

        media_summary = "none"
        try:
            if hasattr(self, "media"):
                m_stat = self.media.status()
                if isinstance(m_stat, dict) and m_stat.get("found"):
                    p_state = m_stat.get("playbackState") or ("paused" if m_stat.get("paused") else "playing")
                    m_title = m_stat.get("title")
                    if m_title and p_state in ("playing", "paused"):
                        media_summary = f"{p_state} ('{m_title}')"
                    else:
                        media_summary = str(p_state)
                elif isinstance(m_stat, dict) and m_stat.get("playbackState") and m_stat.get("playbackState") != "none":
                    media_summary = str(m_stat.get("playbackState"))
        except Exception:
            pass

        return f"[Active Tab: {tab_id_repr} | URL: {url} | Title: {title} | Media: {media_summary}]"


class Chrome(Tab):
    """Global Chrome controller singleton and tab manager.

    Acts as both a fluent handle to the currently active browser tab
    and a manager for tab lifecycle (listing, switching, creating, closing).

    Canonical Composition Lifecycle:
        >>> from chrome_sdk import chrome
        >>> # 1. Inspect open tabs
        >>> print([f"{t.id}: {t.title}" for t in chrome.tabs])
        >>> # 2. Orient on active page
        >>> print(chrome.snapshot())
        >>> # 3. Interact via discovered Ref-ID
        >>> chrome.type("[#1]", "Hello World", press_enter=True)
        >>> # 4. Synchronize and extract
        >>> chrome.wait_for("[#results]")
        >>> print(chrome.get_text("[#results]"))
    """

    def __init__(self, client: Optional[TransportClient] = None):
        super().__init__(tab_id=None, client=client or ChromeSocketClient(), active=True)
        self.safety = global_safety

    def __repr__(self) -> str:
        return "<Chrome active_tab_context>"

    @property
    def tabs(self) -> List[Tab]:
        """List all open browser tabs as scoped Tab handles."""
        tab_dicts = self._client.call("list_tabs")
        return [
            Tab(
                tab_id=t.get("id"),
                client=self._client,
                title=t.get("title", ""),
                url=t.get("url", ""),
                active=t.get("active", False),
            )
            for t in tab_dicts
        ]

    @property
    def active_tab(self) -> Tab:
        """Get handle for the currently active browser tab."""
        tabs = self.tabs
        for t in tabs:
            if t.active:
                return t
        if tabs:
            return tabs[0]
        return Tab(tab_id=None, client=self._client, active=True)

    def tab(self, tab_id: int) -> Tab:
        """Get a scoped Tab handle by integer ID."""
        return Tab(tab_id=tab_id, client=self._client)

    def get_tab(self, tab_id: int) -> Tab:
        """Get a scoped Tab handle by integer ID (alias for tab(tab_id))."""
        return self.tab(tab_id)

    def new_tab(self, url: str = "about:blank") -> Tab:
        """Create and return a new browser tab."""
        res = self._client.call("navigate", {"url": url, "newTab": True})
        return Tab(tab_id=res.get("tabId"), client=self._client, url=res.get("url", url), active=True)

    def ping(self) -> Dict[str, Any]:
        """Ping the active browser session."""
        return self._client.call("ping")

    @property
    def status(self) -> Dict[str, Any]:
        """Check browser connection status."""
        return self._client.call("ping")


# Default global instance
chrome = Chrome()

__all__ = [
    "Chrome",
    "Tab",
    "TabMedia",
    "ElementHandle",
    "chrome",
    "ChromeBridgeError",
    "SecurityException",
    "RunawayLoopDetectedError",
    "BrowserUnavailableError",
    "ElementNotFoundError",
    "ActionInterceptionError",
    "NavigationTimeoutError",
    "TargetLocator",
    "normalize_locator",
    "CRITICAL_DELETION_TERMS",
    "CRITICAL_DELETION_REGEX",
    "SSO_ALLOWLIST",
    "DEFAULT_SOCKET_PATH",
    "DEFAULT_PORT_FILE",
    "SOCKET_PATH",
    "DEFAULT_BROWSER_UNAVAILABLE_MSG",
    "SecurityGateway",
    "SafetyController",
    "ActionTracker",
    "ChromeBridgeWorkerTelemetry",
    "wrap_untrusted_data",
    "defang_telemetry_payload",
    "global_safety",
    "TransportClient",
    "ChromeSocketClient",
    "DomCompiler",
    "DomBatchSynthesizer",
    "resolve_runtime_directory",
    "auto_bootstrap_environment",
]
