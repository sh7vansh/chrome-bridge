"""Unit tests for TransportClient Protocol seam and swappable adapters."""

from typing import Any, Dict, Optional
import pytest
from chrome_bridge.transport import TransportClient, ChromeSocketClient
from chrome_sdk import Chrome, Tab


class InProcessMockTransport:
    """Mock in-process transport satisfying the TransportClient Protocol."""

    def __init__(self):
        self.connected = False
        self.calls = []

    def connect(self, retries: int = 5, backoff: float = 0.2) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def call(self, action: str, params: Optional[Dict[str, Any]] = None, timeout: float = 15.0) -> Any:
        self.calls.append((action, params))
        if action == "list_tabs":
            return [{"id": 1, "title": "Dashboard", "url": "https://test.com", "active": True}]
        if action == "click":
            return {"status": "ok", "action": "click"}
        if action == "get_page_content":
            return {"snapshot": 'PAGE: "Dashboard"\n- button [#1] "Submit"'}
        return {}


def test_transport_client_protocol_satisfaction():
    mock = InProcessMockTransport()
    assert isinstance(mock, TransportClient)
    assert issubclass(ChromeSocketClient, TransportClient) or isinstance(ChromeSocketClient(), TransportClient)


def test_tab_with_in_process_mock_transport():
    mock = InProcessMockTransport()
    chrome = Chrome(client=mock)

    assert chrome.title == ""  # lazy
    snap = chrome.snapshot(wrap=False)
    assert '- button [#1] "Submit"' in snap

    res = chrome.click(1)
    assert res == {"status": "ok", "action": "click"}
    assert ("click", {"target": {"type": "ref", "refId": 1}, "button": "left", "count": 1, "tabId": None}) in mock.calls


def test_ipc_framing_engine_length_prefixed_roundtrip():
    import io
    import struct
    from chrome_bridge.transport import IpcFramingEngine

    payload = {"action": "navigate", "url": "https://example.com", "options": {"timeout": 30}}
    packed = IpcFramingEngine.pack_length_prefixed(payload)
    assert len(packed) >= 4
    length = struct.unpack("<I", packed[:4])[0]
    assert length == len(packed) - 4

    stream = io.BytesIO(packed)
    unpacked = IpcFramingEngine.unpack_length_prefixed_stream(stream)
    assert unpacked == payload


def test_ipc_framing_engine_line_delimited_roundtrip():
    from chrome_bridge.transport import IpcFramingEngine

    msg1 = {"id": 1, "action": "ping"}
    msg2 = {"id": 2, "result": "pong"}

    packed1 = IpcFramingEngine.pack_line_delimited(msg1)
    packed2 = IpcFramingEngine.pack_line_delimited(msg2)
    combined = packed1 + packed2

    # Parse full combined buffer
    msgs, rem = IpcFramingEngine.unpack_line_delimited_buffer(combined)
    assert len(msgs) == 2
    assert msgs[0] == msg1
    assert msgs[1] == msg2
    assert rem == b""

    # Parse partial buffer
    partial = packed1 + b'{"id": 3, "action": '
    msgs_partial, rem_partial = IpcFramingEngine.unpack_line_delimited_buffer(partial)
    assert len(msgs_partial) == 1
    assert msgs_partial[0] == msg1
    assert rem_partial == b'{"id": 3, "action": '

