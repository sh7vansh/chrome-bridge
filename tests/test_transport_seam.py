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


def test_in_process_transport_client_built_in_adapter():
    from chrome_bridge.transport import InProcessTransportClient
    from chrome_bridge.exceptions import ElementNotFoundError

    # Test default fallback handler
    client = InProcessTransportClient()
    assert isinstance(client, TransportClient)
    client.connect()
    assert client.connected is True

    tabs = client.call("list_tabs")
    assert isinstance(tabs, list)
    assert tabs[0]["title"] == "In-Process Tab"

    # Test custom handler with error decoding
    def mock_dispatcher(action: str, params: Optional[Dict[str, Any]]):
        if action == "click":
            return {
                "success": False,
                "error": {
                    "code": "ELEMENT_NOT_FOUND",
                    "target": "[#99]",
                    "message": "Element [#99] not found",
                },
                "auto_snapshot": 'PAGE: "Error Page"\n- button [#1] "Submit"',
            }
        return {"success": True, "result": {"navigated": True}}

    err_client = InProcessTransportClient(handler=mock_dispatcher)
    with pytest.raises(ElementNotFoundError) as exc_info:
        err_client.call("click", {"target": {"type": "ref", "refId": 99}})

    assert exc_info.value.target == "[#99]"
    assert 'PAGE: "Error Page"' in (exc_info.value.auto_snapshot or "")

    res = err_client.call("navigate", {"url": "https://example.com"})
    assert res == {"navigated": True}
    client.close()
    assert client.connected is False


def test_native_ipc_server_facade_and_exports():
    import native_host
    from chrome_bridge.transport import NativeIpcServer, NativeHostBridge

    assert native_host.NativeIpcServer is NativeIpcServer
    assert native_host.NativeHostBridge is NativeHostBridge
    assert hasattr(native_host, "send_native_message")
    assert hasattr(native_host, "cleanup_ipc_endpoints")


