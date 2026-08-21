"""Zero-latency 5-layer security gateway and defense pipeline for Chrome Bridge."""

import contextlib
import re
import time
from collections import deque
from typing import Any, Dict, List, Optional, Set, Union

from .exceptions import (
    CRITICAL_DELETION_REGEX,
    SSO_ALLOWLIST,
    RunawayLoopDetectedError,
    SecurityException,
    _extract_hostname,
)


def wrap_untrusted_data(content: str, origin: str = "", selector: str = "body") -> str:
    """Wrap raw page content in strict XML structural boundaries and defang tag-breakout attempts."""
    s_content = content if isinstance(content, str) else str(content)
    if "</UNTRUSTED_EXTERNAL_DATA>" in s_content:
        s_content = s_content.replace("</UNTRUSTED_EXTERNAL_DATA>", "&lt;/UNTRUSTED_EXTERNAL_DATA&gt;")
    safe_origin = origin if isinstance(origin, str) else str(origin)
    if '"' in safe_origin:
        safe_origin = safe_origin.replace('"', '&quot;')
    safe_selector = selector if isinstance(selector, str) else str(selector)
    if '"' in safe_selector:
        safe_selector = safe_selector.replace('"', '&quot;')
    return f'<UNTRUSTED_EXTERNAL_DATA origin="{safe_origin}" selector="{safe_selector}">\n{s_content}\n</UNTRUSTED_EXTERNAL_DATA>'


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


class _TabActionTracker:
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


class SecurityGateway:
    """Centralized, deep zero-latency security gateway and policy enforcement module.

    Encapsulates the complete 5-layer defense pipeline:
    1. Untrusted Data Boundary Framing (wrap_untrusted_data / sanitize_inbound)
    2. Hardcoded Deletion Safety Valve (permit_destructive context manager / verify_action)
    3. Origin & SSO Locking (allow_origin / is_origin_allowed)
    4. Telemetry & Media Defanging (defang_telemetry_payload / sanitize_outbound)
    5. Sliding-Window Anti-DoS Action Tracker (tab-sharded ring buffers)
    """

    def __init__(self):
        self._permit_destructive_depth = 0
        self._allowed_origins: Set[str] = set()
        self._tab_trackers: Dict[Any, _TabActionTracker] = {}
        self._default_tracker = _TabActionTracker()

    @contextlib.contextmanager
    def permit_destructive(self):
        """Context manager to temporarily bypass destructive action safety valves.

        Example:
            >>> with chrome.safety.permit_destructive():
            ...     chrome.click("[#confirm-delete]")
        """
        self._permit_destructive_depth += 1
        try:
            yield
        finally:
            self._permit_destructive_depth = max(0, self._permit_destructive_depth - 1)

    @property
    def is_destructive_permitted(self) -> bool:
        """Return True if destructive operations are currently permitted within a context manager."""
        return self._permit_destructive_depth > 0

    def allow_origin(self, url_or_domain: str) -> None:
        """Allow navigations to the specified hostname or domain."""
        host = _extract_hostname(url_or_domain)
        if host:
            self._allowed_origins.add(host.lower())

    def is_origin_allowed(self, host: str, tab_origins: Optional[Set[str]] = None) -> bool:
        """Check whether a given hostname is permitted under current task scope and SSO allowlists."""
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

    def get_tracker_for_tab(self, tab_id: Optional[int]) -> _TabActionTracker:
        """Retrieve or create tab-partitioned action tracker."""
        if tab_id is None:
            return self._default_tracker
        if tab_id not in self._tab_trackers:
            self._tab_trackers[tab_id] = _TabActionTracker()
        return self._tab_trackers[tab_id]

    def verify_action(
        self,
        action: str,
        target: Any = None,
        url: str = "",
        tab_id: Optional[int] = None,
        text: str = "",
        safety_check: bool = True,
    ) -> None:
        """Enforce Layer 2 (Destructive Actions) and Layer 5 (Anti-DoS sliding window) checks."""
        if safety_check and not self.is_destructive_permitted:
            target_str = str(target) if target is not None else ""
            if CRITICAL_DELETION_REGEX.search(target_str):
                raise SecurityException(
                    f"Destructive action blocked: Target '{target_str}' matches critical deletion pattern.",
                    status="BLOCKED_DESTRUCTIVE_ACTION",
                    tab_id=tab_id,
                )
            if text and CRITICAL_DELETION_REGEX.search(text):
                raise SecurityException(
                    f"Destructive action blocked: Input text '{text}' matches critical deletion pattern.",
                    status="BLOCKED_DESTRUCTIVE_ACTION",
                    tab_id=tab_id,
                )

        tracker = self.get_tracker_for_tab(tab_id)
        tracker.record_and_validate(action, target, url, tab_id=tab_id)

    def verify_navigation(
        self,
        url: str,
        current_url: str = "",
        tab_origins: Optional[Set[str]] = None,
        tab_id: Optional[int] = None,
        safety_check: bool = True,
    ) -> None:
        """Enforce Layer 3 (Origin Locking) policy for page navigations."""
        target_host = _extract_hostname(url)
        if safety_check and target_host:
            effective_origins = set(tab_origins) if tab_origins else set()
            if current_url:
                current_host = _extract_hostname(current_url)
                if current_host:
                    effective_origins.add(current_host)

            if effective_origins and not self.is_origin_allowed(target_host, effective_origins):
                raise SecurityException(
                    f"Navigation blocked: '{url}' is outside task scope.",
                    status="BLOCKED_ORIGIN_VIOLATION",
                    tab_id=tab_id,
                )

    def sanitize_inbound(self, content: str, origin: str = "", selector: str = "body") -> str:
        """Enforce Layer 1 (Untrusted Data Isolation Boundary)."""
        return wrap_untrusted_data(content, origin=origin, selector=selector)

    def sanitize_outbound(self, payload: Any) -> Any:
        """Enforce Layer 4 (Markdown Image Beacon and HTML Defanging)."""
        return defang_telemetry_payload(payload)


# Global singleton instance
global_safety = SecurityGateway()

# Backward-compatible facades
SafetyController = SecurityGateway
ActionTracker = _TabActionTracker
