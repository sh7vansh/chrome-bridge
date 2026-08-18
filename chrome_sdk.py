"""Synchronous Python SDK and IPC Client for Chrome Bridge."""

import contextlib
import json
import os
import re
import socket
import sys
import time
from collections import deque
from typing import Any, Dict, List, Optional, Union

import tempfile

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

DEFAULT_SOCKET_PATH = os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.sock")
DEFAULT_PORT_FILE = os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.port")
SOCKET_PATH = DEFAULT_SOCKET_PATH
PORT_FILE = DEFAULT_PORT_FILE
TargetLocator = Union[int, str]


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


def wrap_untrusted_data(content: str, origin: str = "", selector: str = "body") -> str:
    """Wrap raw page content in strict XML structural boundaries and defang tag-breakout attempts."""
    safe_content = str(content).replace("</UNTRUSTED_EXTERNAL_DATA>", "&lt;/UNTRUSTED_EXTERNAL_DATA&gt;")
    safe_origin = str(origin).replace('"', '&quot;')
    safe_selector = str(selector).replace('"', '&quot;')
    return (
        f'<UNTRUSTED_EXTERNAL_DATA origin="{safe_origin}" selector="{safe_selector}">\n'
        f'{safe_content}\n'
        f'</UNTRUSTED_EXTERNAL_DATA>'
    )


def defang_telemetry_payload(data: Any) -> Any:
    """Recursively defang remote markdown image beacons and HTML active tags."""
    if isinstance(data, str):
        # Defang markdown image beacon: ![alt](url) -> [IMAGE_BLOCKED: alt | url]
        s = re.sub(r"!\[(.*?)\]\((https?://[^\)]+)\)", r"[IMAGE_BLOCKED: \1 | \2]", data)
        # Defang HTML media / active elements
        s = re.sub(r"<(img|iframe|link)\b([^>]*)>", r"[TAG_BLOCKED: \1\2]", s, flags=re.IGNORECASE)
        s = re.sub(r"</(img|iframe|link)>", r"", s, flags=re.IGNORECASE)
        return s
    elif isinstance(data, dict):
        return {k: defang_telemetry_payload(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [defang_telemetry_payload(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(defang_telemetry_payload(item) for item in data)
    return data


class ChromeBridgeWorkerTelemetry:
    """Structured telemetry schema for subagent worker return payloads."""

    def __init__(
        self,
        tab_id: Optional[int] = None,
        origin: str = "",
        url: str = "",
        title: str = "",
        status: str = "success",
        extracted_data: Any = None,
        count: int = 0,
        execution_ms: float = 0.0,
        media_state: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        self.tab_id = tab_id
        self.origin = origin
        self.url = url
        self.title = title
        self.status = status
        self.extracted_data = extracted_data
        self.count = count
        self.execution_ms = execution_ms
        self.media_state = media_state
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tab_id": self.tab_id,
            "origin": self.origin,
            "url": self.url,
            "title": self.title,
            "status": self.status,
            "extracted_data": defang_telemetry_payload(self.extracted_data),
            "count": self.count,
            "execution_ms": self.execution_ms,
            "media_state": self.media_state,
            "error": self.error,
        }


class SafetyController:
    """Zero-overhead safety and origin governance controller."""

    def __init__(self):
        self._permit_destructive_depth = 0
        self._allowed_origins: set = set()

    @contextlib.contextmanager
    def permit_destructive(self):
        self._permit_destructive_depth += 1
        try:
            yield
        finally:
            self._permit_destructive_depth = max(0, self._permit_destructive_depth - 1)

    @property
    def is_destructive_permitted(self) -> bool:
        return self._permit_destructive_depth > 0

    def allow_origin(self, url_or_domain: str) -> None:
        host = _extract_hostname(url_or_domain)
        if host:
            self._allowed_origins.add(host.lower())

    def is_origin_allowed(self, host: str, tab_origins: Optional[set] = None) -> bool:
        if not host or host in ("about:blank", "localhost", "127.0.0.1"):
            return True
        h = host.lower()
        if h in SSO_ALLOWLIST:
            return True
        for sso in SSO_ALLOWLIST:
            if h.endswith("." + sso):
                return True
        if h in self._allowed_origins:
            return True
        for allowed in self._allowed_origins:
            if h == allowed or h.endswith("." + allowed):
                return True
        if tab_origins:
            for orig in tab_origins:
                if h == orig or h.endswith("." + orig):
                    return True
        return False


class ActionTracker:
    """Sliding-window ring buffer to intercept repetitive clicks, oscillations, and runaway scrolling."""

    def __init__(self, maxlen: int = 20):
        self.history = deque(maxlen=maxlen)
        self.consecutive_scrolls = 0

    def record_and_validate(self, action: str, target: Any, url: str, tab_id: Optional[int] = None) -> None:
        now = time.time()
        target_key = str(target) if target is not None else ""

        if action == "scroll":
            self.consecutive_scrolls += 1
            if self.consecutive_scrolls > 10:
                raise RunawayLoopDetectedError(
                    f"Runaway scroll detected: {self.consecutive_scrolls} consecutive scrolls without interaction.",
                    tab_id=tab_id,
                )
        else:
            self.consecutive_scrolls = 0

        # Repetitive click cap: >= 5 identical target clicks within 15s
        if action in ("click", "click_ref"):
            recent_clicks = [
                (t, act, tgt)
                for (t, act, tgt, u) in self.history
                if act in ("click", "click_ref") and tgt == target_key and (now - t) <= 15.0
            ]
            if len(recent_clicks) >= 4:
                raise RunawayLoopDetectedError(
                    f"Repetitive click loop detected on target '{target_key}' (5 identical clicks within 15s).",
                    tab_id=tab_id,
                )

        # Ping-pong oscillation: A -> B -> A -> B -> A -> (attempting B) -> 6 steps
        if action in ("click", "click_ref"):
            actions = list(self.history)[-5:]
            if len(actions) == 5:
                _, a0, tg0, _ = actions[0]
                _, a1, tg1, _ = actions[1]
                _, a2, tg2, _ = actions[2]
                _, a3, tg3, _ = actions[3]
                _, a4, tg4, _ = actions[4]
                if (
                    tg0 == tg2 == tg4 != tg1
                    and tg1 == tg3 == target_key
                    and a0 == a1 == a2 == a3 == a4 == action
                ):
                    raise RunawayLoopDetectedError(
                        f"Ping-pong oscillation detected between '{tg0}' and '{target_key}'.",
                        tab_id=tab_id,
                    )

        self.history.append((now, action, target_key, url))


global_safety = SafetyController()


DEFAULT_BROWSER_UNAVAILABLE_MSG = (
    "Browser instance is not reachable or session disconnected.\n\n"
    "Troubleshooting checklist:\n"
    "  1. Ensure Google Chrome is open and running.\n"
    "  2. Verify Chrome Bridge is active in Chrome.\n"
    "  3. Re-run setup on this machine: node setup-host.mjs or ./setup.sh"
)


class BrowserUnavailableError(ChromeBridgeError):
    """Raised when the browser is not running, unreachable, or disconnected."""

    def __init__(
        self,
        message: str = DEFAULT_BROWSER_UNAVAILABLE_MSG,
        tab_id: Optional[int] = None,
    ):
        super().__init__(message, tab_id)


def _format_ref_id(ref: Union[str, int]) -> str:
    """Format a Ref-ID into canonical [#X] representation."""
    r_str = str(ref).strip()
    if not r_str.startswith("#") and not r_str.startswith("[#"):
        r_str = f"#{r_str}"
    if not r_str.startswith("["):
        r_str = f"[{r_str}]"
    return r_str


class ElementNotFoundError(ChromeBridgeError):
    """Raised when a Ref-ID or CSS selector cannot be located."""

    def __init__(
        self,
        target: str,
        tab_id: Optional[int] = None,
        stale: bool = False,
        suggestions: Optional[List[Dict[str, Any]]] = None,
        url: str = "",
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


class NavigationTimeoutError(ChromeBridgeError):
    """Raised when navigation or element condition waiting exceeds deadline."""

    def __init__(
        self,
        target: Optional[str] = None,
        timeout: float = 10.0,
        url: str = "",
        ready_state: str = "unknown",
        dom_state: str = "unknown",
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


class ChromeSocketClient:
    """Synchronous IPC client for Chrome Bridge native host."""

    def __init__(self, socket_path: str = SOCKET_PATH, port_file: Optional[str] = None):
        self.socket_path = socket_path
        if port_file is not None:
            self.port_file = port_file
        elif socket_path != DEFAULT_SOCKET_PATH:
            self.port_file = os.path.splitext(socket_path)[0] + ".port"
        else:
            self.port_file = DEFAULT_PORT_FILE
        self._sock: Optional[socket.socket] = None
        self._req_id = 0
        self._buffer = b""

    def connect(self, retries: int = 5, backoff: float = 0.2) -> None:
        if self._sock:
            return

        use_tcp = os.name == "nt" or not hasattr(socket, "AF_UNIX")

        for i in range(retries):
            try:
                if use_tcp:
                    if not os.path.exists(self.port_file):
                        raise FileNotFoundError(f"Port file '{self.port_file}' does not exist.")
                    with open(self.port_file, "r", encoding="utf-8", errors="replace") as f:
                        port_str = f.read().strip()
                    if not port_str:
                        raise ValueError("Port file is empty.")
                    port = int(port_str)
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect(("127.0.0.1", port))
                else:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(self.socket_path)
                s.settimeout(20.0)
                self._sock = s
                return
            except (socket.error, FileNotFoundError, ValueError) as err:
                if i == retries - 1:
                    raise BrowserUnavailableError() from err
                time.sleep(backoff * (i + 1))

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            self._buffer = b""

    def call(self, action: str, params: Optional[Dict[str, Any]] = None, timeout: float = 15.0) -> Any:
        self.connect()
        self._req_id += 1
        req_id = self._req_id
        req_payload = {
            "id": req_id,
            "action": action,
            "params": params or {},
        }
        data = json.dumps(req_payload) + "\n"

        try:
            assert self._sock is not None
            self._sock.settimeout(timeout)
            self._sock.sendall(data.encode("utf-8"))

            while True:
                # Check buffer for a complete line
                if b"\n" in self._buffer:
                    line, self._buffer = self._buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    resp = json.loads(line.decode("utf-8", errors="replace"))
                    if resp.get("id") == req_id:
                        if not resp.get("success", False):
                            self._raise_structured_error(resp, params)
                        return resp.get("result")

                chunk = self._sock.recv(65536)
                if not chunk:
                    raise BrowserUnavailableError("Browser session disconnected unexpectedly.")
                self._buffer += chunk

        except socket.timeout:
            self.close()
            raise NavigationTimeoutError(
                target=str(params.get("target") if params else action),
                timeout=timeout,
                url=params.get("url", "") if params else "",
            )
        except Exception as e:
            if isinstance(e, ChromeBridgeError):
                raise
            self.close()
            raise BrowserUnavailableError(f"Browser communication error during '{action}'.") from e

    def _raise_structured_error(self, resp: Dict[str, Any], params: Optional[Dict[str, Any]]) -> None:
        err_data = resp.get("error")
        auto_snapshot = resp.get("auto_snapshot")
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



class TabMedia:
    """Fast-path media controller attached to a Tab instance."""

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
        js = f"""
        (() => {{
            {self._FIND_MEDIA_JS}

            const media = findMediaElement();
            const session = navigator.mediaSession;
            return {{
                found: !!media,
                paused: media ? media.paused : null,
                currentTime: media ? media.currentTime : null,
                duration: media ? media.duration : null,
                volume: media ? media.volume : null,
                muted: media ? media.muted : null,
                title: session?.metadata?.title || document.title,
                artist: session?.metadata?.artist || "",
                album: session?.metadata?.album || "",
                playbackState: session?.playbackState || (media ? (media.paused ? "paused" : "playing") : "none")
            }};
        }})()
        """
        return self._tab.eval_js(js) or {}

    def toggle(self) -> Dict[str, Any]:
        """Toggle play/pause on the active media element."""
        js = f"""
        (() => {{
            {self._FIND_MEDIA_JS}
            const media = findMediaElement();
            if (!media) return {{success: false, error: "No media element found"}};
            if (media.paused) {{
                media.play();
                return {{success: true, action: "played"}};
            }} else {{
                media.pause();
                return {{success: true, action: "paused"}};
            }}
        }})()
        """
        return self._tab.eval_js(js) or {}

    def play(self) -> Dict[str, Any]:
        """Play active media element."""
        js = f"""
        (() => {{
            {self._FIND_MEDIA_JS}
            const v = findMediaElement();
            if (v) {{ v.play(); return {{success: true}}; }}
            return {{success: false, error: "No media element found"}};
        }})()
        """
        return self._tab.eval_js(js) or {}

    def pause(self) -> Dict[str, Any]:
        """Pause active media element."""
        js = f"""
        (() => {{
            {self._FIND_MEDIA_JS}
            const v = findMediaElement();
            if (v) {{ v.pause(); return {{success: true}}; }}
            return {{success: false, error: "No media element found"}};
        }})()
        """
        return self._tab.eval_js(js) or {}

    def seek(self, seconds: float) -> Dict[str, Any]:
        """Seek relative (+/- seconds) or absolute position."""
        js = f"""
        (() => {{
            {self._FIND_MEDIA_JS}
            const v = findMediaElement();
            if (!v) return {{success: false, error: "No media element found"}};
            v.currentTime += {float(seconds)};
            return {{success: true, currentTime: v.currentTime}};
        }})()
        """
        return self._tab.eval_js(js) or {}

    def set_volume(self, volume: float) -> Dict[str, Any]:
        """Set volume level between 0.0 and 1.0."""
        volume = max(0.0, min(1.0, float(volume)))
        js = f"""
        (() => {{
            {self._FIND_MEDIA_JS}
            const v = findMediaElement();
            if (v) {{ v.volume = {volume}; v.muted = false; return {{success: true, volume: v.volume}}; }}
            return {{success: false, error: "No media element found"}};
        }})()
        """
        return self._tab.eval_js(js) or {}


class Tab:
    """Scoped browser tab handle and procedural action context."""

    def __init__(
        self,
        tab_id: Optional[int] = None,
        client: Optional[ChromeSocketClient] = None,
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
        self.allowed_origins: set = set()
        if self.url:
            host = _extract_hostname(self.url)
            if host:
                self.allowed_origins.add(host)
        self._action_tracker = ActionTracker()
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
        if safety_check and not self.safety.is_destructive_permitted:
            target_str = str(target) if target is not None else ""
            if CRITICAL_DELETION_REGEX.search(target_str):
                raise SecurityException(
                    f"Destructive action blocked: Target '{target_str}' matches critical deletion pattern.",
                    status="BLOCKED_DESTRUCTIVE_ACTION",
                    tab_id=self.id,
                )
            if text and CRITICAL_DELETION_REGEX.search(text):
                raise SecurityException(
                    f"Destructive action blocked: Input text '{text}' matches critical deletion pattern.",
                    status="BLOCKED_DESTRUCTIVE_ACTION",
                    tab_id=self.id,
                )

        self._action_tracker.record_and_validate(action, target, self.url, tab_id=self.id)

    def activate(self) -> Dict[str, Any]:
        """Focus and switch to this tab."""
        return self._client.call("switch_tab", {"tabId": self.id})

    def close(self) -> Dict[str, Any]:
        """
        Safely closes the tab. If this is the last open tab in the browser,
        it spawns a clean 'about:blank' tab first to prevent Chrome from
        terminating the entire window and severing the bridge connection.
        """
        try:
            tabs = self._client.call("list_tabs")
            if isinstance(tabs, list) and len(tabs) <= 1:
                self._client.call("navigate", {"url": "about:blank", "newTab": True})
            return self._client.call("close_tab", {"tabId": self.id})
        except Exception:
            # Fallback to direct close if tab listing fails
            return self._client.call("close_tab", {"tabId": self.id})

    def navigate(self, url: str, timeout: float = 30.0, safety_check: bool = True) -> Dict[str, Any]:
        """
        Navigates the tab to the specified URL while neutralizing
        any 'beforeunload' dialogs (e.g., Leave/Stay prompts).
        """
        target_host = _extract_hostname(url)
        if safety_check and target_host:
            tab_origins = set(self.allowed_origins)
            if self.url:
                current_host = _extract_hostname(self.url)
                if current_host:
                    tab_origins.add(current_host)

            if tab_origins and not self.safety.is_origin_allowed(target_host, tab_origins):
                raise SecurityException(
                    f"Navigation blocked: '{url}' is outside task scope.",
                    status="BLOCKED_ORIGIN_VIOLATION",
                    tab_id=self.id,
                )

        try:
            self.eval_js("""
                window.onbeforeunload = null;
                window.addEventListener('beforeunload', (e) => {
                    e.stopImmediatePropagation();
                }, true);
            """)
        except Exception:
            # Ignore errors if page is not in a valid JS state or already unloading
            pass

        res = self._client.call("navigate", {"url": url, "tabId": self.id}, timeout=timeout)
        self.url = res.get("url", url) if isinstance(res, dict) else url
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

    def snapshot(self, compact: bool = True, wrap: bool = True) -> str:
        """Generate a token-optimized Semantic DOM Snapshot with Ref-IDs."""
        res = self._client.call("get_page_content", {"tabId": self.id, "compact": compact})
        raw = res.get("snapshot", "") if isinstance(res, dict) else str(res)
        if wrap:
            return wrap_untrusted_data(raw, origin=self.origin, selector="document")
        return raw

    def click(
        self,
        target: TargetLocator,
        button: str = "left",
        count: int = 1,
        safety_check: bool = True,
    ) -> Dict[str, Any]:
        """Click an element by Ref-ID or CSS selector."""
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
        """Type text into an input or contenteditable element."""
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
        """Press a keyboard key."""
        self._safety_check_action("press_key", key, safety_check=safety_check)
        return self._client.call("press_key", {"key": key, "tabId": self.id})

    def select(self, target: TargetLocator, value: str, safety_check: bool = True) -> Dict[str, Any]:
        """Select an option in a dropdown."""
        self._safety_check_action("select", target, text=value, safety_check=safety_check)
        loc = normalize_locator(target)
        return self._client.call("select_option", {"target": loc, "value": value, "tabId": self.id})

    def hover(self, target: TargetLocator) -> Dict[str, Any]:
        """Hover mouse over an element."""
        loc = normalize_locator(target)
        return self._client.call("hover", {"target": loc, "tabId": self.id})

    def scroll(self, x: int = 0, y: int = 500, target: Optional[TargetLocator] = None) -> Dict[str, Any]:
        """Scroll the page or a specific container."""
        self._action_tracker.record_and_validate("scroll", target, self.url, tab_id=self.id)
        loc = normalize_locator(target) if target is not None else None
        return self._client.call("scroll", {"x": x, "y": y, "target": loc, "tabId": self.id})

    def get_text(self, target: TargetLocator, wrap: bool = True) -> str:
        """Get inner text of an element."""
        loc = normalize_locator(target)
        res = self._client.call("get_text", {"target": loc, "tabId": self.id})
        raw = res.get("text", "") if isinstance(res, dict) else str(res)
        if wrap:
            return wrap_untrusted_data(raw, origin=self.origin, selector=str(target))
        return raw

    def get_attribute(self, target: TargetLocator, name: str) -> Optional[str]:
        """Get DOM attribute value."""
        loc = normalize_locator(target)
        res = self._client.call("get_attribute", {"target": loc, "name": name, "tabId": self.id})
        return res.get("value") if isinstance(res, dict) else None

    def eval_js(self, script: str, target: Optional[TargetLocator] = None) -> Any:
        """Execute JavaScript in page context."""
        loc = normalize_locator(target) if target is not None else None
        return self._client.call("execute_script", {"code": script, "target": loc, "tabId": self.id})

    def screenshot(self, path: Optional[str] = None) -> str:
        """Capture page screenshot."""
        res = self._client.call("screenshot", {"path": path, "tabId": self.id})
        return res.get("dataUrl") or res.get("data", "")

    def wait_for(self, target: TargetLocator, timeout: float = 10.0, state: str = "visible") -> bool:
        """Synchronously wait for an element to reach the desired state ('visible', 'hidden', 'attached')."""
        loc = normalize_locator(target)
        return self._client.call(
            "wait_for",
            {"target": loc, "state": state, "timeout": timeout, "tabId": self.id},
            timeout=timeout + 3.0,
        )

    def wait_for_url(self, pattern: str, timeout: float = 15.0) -> bool:
        """Synchronously wait for current URL to match regex pattern."""
        return self._client.call(
            "wait_for_url",
            {"pattern": pattern, "timeout": timeout, "tabId": self.id},
            timeout=timeout + 3.0,
        )


class Chrome(Tab):
    """Global Chrome singleton providing fluent active tab control and tab management."""

    def __init__(self, client: Optional[ChromeSocketClient] = None):
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
        # Fallback tab handle with id=None
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

