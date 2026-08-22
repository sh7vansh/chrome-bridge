"""Domain exceptions and locator normalization utilities for Chrome Bridge."""

import os
import re
import tempfile
from typing import Any, Dict, List, Optional, Union

DEFAULT_SOCKET_PATH = os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.sock")
DEFAULT_PORT_FILE = os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.port")
SOCKET_PATH = DEFAULT_SOCKET_PATH

DEFAULT_BROWSER_UNAVAILABLE_MSG = (
    "Browser instance is not reachable or session disconnected.\n\n"
    "Troubleshooting checklist:\n"
    "  1. Ensure Google Chrome is open and running.\n"
    "  2. Verify Chrome Bridge is active in Chrome.\n"
    "  3. Re-run setup on this machine: uvx antigravity-chrome-bridge setup or ./setup.sh"
)

TargetLocator = Union[int, str]
"""Target locator for DOM elements.

Accepts:
- int: Integer Ref-ID from snapshot (e.g. 14)
- str: Bracketed Ref-ID token (e.g. "[#14]")
- str: Hash Ref-ID token (e.g. "#14")
- str: Standard CSS selector (e.g. "button.submit", "input[name='q']", "#main-btn")
"""

CRITICAL_DELETION_TERMS = [
    r"\bdelete[-_\s]+account\b",
    r"\bcancel[-_\s]+account\b",
    r"\bclose[-_\s]+account\b",
    r"\bdelete[-_\s]+organization\b",
    r"\bdelete[-_\s]+org\b",
    r"\bterminate[-_\s]+subscription\b",
    r"\bcancel[-_\s]+subscription\b",
    r"\bpurge[-_\s]+database\b",
    r"\bdrop[-_\s]+database\b",
    r"\bdelete[-_\s]+repository\b",
    r"\bdelete[-_\s]+repo\b",
    r"\bwipe[-_\s]+data\b",
]
CRITICAL_DELETION_REGEX = re.compile("|".join(CRITICAL_DELETION_TERMS), re.IGNORECASE)

SSO_ALLOWLIST = {
    "accounts.google.com",
    "github.com",
    "login.microsoftonline.com",
    "appleid.apple.com",
    "auth0.com",
    "login.live.com",
    "auth.github.com",
    "gitlab.com",
}


def _extract_hostname(url: str) -> str:
    """Extract clean lowercase hostname from URL or domain string."""
    if not url:
        return ""
    if url == "about:blank" or url.startswith("chrome://"):
        return ""
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc:
        return parsed.netloc.split(":")[0].lower()
    if not parsed.scheme and "/" not in url:
        return url.split(":")[0].lower()
    return ""


def _format_ref_id(ref: Union[str, int]) -> str:
    """Format a Ref-ID into canonical [#X] representation."""
    r_str = str(ref).strip()
    if not r_str.startswith("#") and not r_str.startswith("[#"):
        r_str = f"#{r_str}"
    if not r_str.startswith("["):
        r_str = f"[{r_str}]"
    return r_str


def normalize_locator(target: TargetLocator) -> Dict[str, Any]:
    """Normalize integer, Ref-ID string, or CSS selector into an IPC target payload."""
    if isinstance(target, int):
        return {"type": "ref", "refId": target}

    target_str = str(target).strip()

    # Matches [#12] or [# 12]
    m_bracket = re.match(r"^\[#\s*(\d+)\]$", target_str)
    if m_bracket:
        return {"type": "ref", "refId": int(m_bracket.group(1))}

    # Matches #12 (pure number following #)
    m_hash = re.match(r"^#(\d+)$", target_str)
    if m_hash:
        return {"type": "ref", "refId": int(m_hash.group(1))}

    # Matches ref:12 or ref=12
    m_ref = re.match(r"^ref[:=](\d+)$", target_str, re.IGNORECASE)
    if m_ref:
        return {"type": "ref", "refId": int(m_ref.group(1))}

    # Standard CSS selector
    return {"type": "css", "selector": target_str}


class ChromeBridgeError(Exception):
    """Base exception for all Chrome Bridge operations."""

    def __init__(self, message: str, tab_id: Optional[int] = None):
        super().__init__(message)
        self.tab_id = tab_id
        self.auto_snapshot: Optional[str] = None


class SecurityException(ChromeBridgeError):
    """Raised when an operation violates Chrome Bridge zero-latency security policies."""

    def __init__(
        self,
        message: str,
        status: str = "BLOCKED_SECURITY_VIOLATION",
        tab_id: Optional[int] = None,
    ):
        super().__init__(message, tab_id=tab_id)
        self.status = status


class RunawayLoopDetectedError(SecurityException):
    """Raised when a repetitive action, oscillation, or scroll runaway loop is detected."""

    def __init__(
        self,
        message: str,
        status: str = "RUNAWAY_LOOP_DETECTED",
        tab_id: Optional[int] = None,
    ):
        super().__init__(message, status=status, tab_id=tab_id)


class BrowserUnavailableError(ChromeBridgeError):
    """Raised when the browser is not running, unreachable, or disconnected."""

    def __init__(
        self,
        message: str = DEFAULT_BROWSER_UNAVAILABLE_MSG,
        tab_id: Optional[int] = None,
    ):
        super().__init__(message, tab_id)


class ElementNotFoundError(ChromeBridgeError):
    """Raised when a Ref-ID or CSS selector cannot be located."""

    def __init__(
        self,
        target: str,
        tab_id: Optional[int] = None,
        stale: bool = False,
        suggestions: Optional[List[Dict[str, Any]]] = None,
        url: str = "",
        auto_snapshot: Optional[str] = None,
    ):
        tab_str = f" in tab {tab_id}" if tab_id is not None else ""
        url_str = f" (URL: {url})" if url else ""
        msg = f"Element matching '{target}' not found{tab_str}{url_str}."
        if stale:
            msg += " The DOM mutated since the last snapshot was generated."
        if suggestions:
            sug_list = []
            for s in suggestions:
                ref = _format_ref_id(s.get("ref", ""))
                role = s.get("role", "element")
                name = s.get("name", "")
                sug_list.append(f"{ref} ({role} '{name}')")
            msg += f" Did you mean: {', '.join(sug_list)}?"

        super().__init__(msg, tab_id)
        self.auto_snapshot = auto_snapshot
        self.target = target
        self.stale = stale
        self.suggestions = suggestions or []
        self.url = url


class ActionInterceptionError(ChromeBridgeError):
    """Raised when coordinate hit-testing is intercepted by an overlapping element."""

    def __init__(
        self,
        target: str,
        interceptor_tag: str = "",
        interceptor_ref: Optional[Union[str, int]] = None,
        interceptor_desc: str = "",
        tab_id: Optional[int] = None,
    ):
        ref_formatted = _format_ref_id(interceptor_ref) if interceptor_ref is not None else ""

        interceptor_label = (
            f"{ref_formatted} ({interceptor_desc})"
            if ref_formatted
            else (f"<{interceptor_tag}> ({interceptor_desc})" if interceptor_desc else f"<{interceptor_tag}>")
        )
        tab_str = f" in tab {tab_id}" if tab_id is not None else ""
        msg = (
            f"Click on target '{target}' was intercepted by overlapping element "
            f"{interceptor_label}{tab_str}. Dismiss or close the overlay before interacting with the target."
        )
        super().__init__(msg, tab_id)
        self.target = target
        self.interceptor_tag = interceptor_tag
        self.interceptor_ref = interceptor_ref
        self.interceptor_desc = interceptor_desc


class NavigationTimeoutError(ChromeBridgeError):
    """Raised when page navigation, wait_for, or wait_for_url condition times out."""

    def __init__(
        self,
        target: str = "",
        timeout: float = 10.0,
        url: str = "",
        ready_state: str = "",
        dom_state: str = "",
        tab_id: Optional[int] = None,
    ):
        tab_str = f" in tab {tab_id}" if tab_id is not None else ""
        msg = f"Timed out after {timeout:.1f}s waiting for '{target or url}'{tab_str}."
        if url or ready_state or dom_state:
            msg += f" (Current URL: {url}, readyState: '{ready_state}', DOM state: '{dom_state}')"
        super().__init__(msg, tab_id)
        self.timeout = timeout
        self.url = url
        self.ready_state = ready_state
        self.dom_state = dom_state


def decode_domain_error(
    err_data: Any,
    params: Optional[Dict[str, Any]] = None,
    auto_snapshot: Optional[str] = None,
) -> None:
    """Decode backend error JSON payload into domain exceptions with auto-snapshot recovery."""
    if isinstance(err_data, dict) and not auto_snapshot:
        auto_snapshot = err_data.get("auto_snapshot")

    target_loc = params.get("target") if params else None
    target_str = ""
    if isinstance(target_loc, dict):
        if target_loc.get("type") == "ref":
            target_str = f"[#{target_loc.get('refId')}]"
        else:
            target_str = str(target_loc.get("selector", ""))
    elif target_loc is not None:
        target_str = str(target_loc)

    tab_id = params.get("tabId") if params else None

    exc = None
    if isinstance(err_data, dict):
        code = err_data.get("code") or err_data.get("name")
        if code == "ELEMENT_NOT_FOUND" or "not found" in str(err_data.get("message", "")).lower():
            exc = ElementNotFoundError(
                target=err_data.get("target", target_str),
                tab_id=err_data.get("tabId", tab_id),
                stale=err_data.get("stale", False),
                suggestions=err_data.get("suggestions", []),
                url=err_data.get("url", ""),
            )
        elif code == "ACTION_INTERCEPTED":
            exc = ActionInterceptionError(
                target=err_data.get("target", target_str),
                interceptor_tag=err_data.get("interceptorTag", "overlay"),
                interceptor_ref=err_data.get("interceptorRef"),
                interceptor_desc=err_data.get("interceptorDesc", ""),
                tab_id=err_data.get("tabId", tab_id),
            )
        elif code == "TIMEOUT":
            exc = NavigationTimeoutError(
                target=err_data.get("target", target_str),
                timeout=err_data.get("timeout", 10.0),
                url=err_data.get("url", ""),
                ready_state=err_data.get("readyState", "unknown"),
                dom_state=err_data.get("domState", "unknown"),
                tab_id=err_data.get("tabId", tab_id),
            )
        else:
            exc = ChromeBridgeError(err_data.get("message", str(err_data)), tab_id=tab_id)
    else:
        err_str = str(err_data)
        if "not found" in err_str.lower():
            exc = ElementNotFoundError(target=target_str, tab_id=tab_id)
        elif "intercepted" in err_str.lower():
            exc = ActionInterceptionError(target=target_str, tab_id=tab_id)
        elif "timed out" in err_str.lower():
            exc = NavigationTimeoutError(target=target_str, tab_id=tab_id)
        else:
            exc = ChromeBridgeError(err_str, tab_id=tab_id)

    if auto_snapshot and exc:
        exc.auto_snapshot = auto_snapshot
    if exc:
        raise exc
