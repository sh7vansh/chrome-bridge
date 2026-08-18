"""Tests for pure Python native_host.py: framing, IPC routing, request ID tracking, lifecycle cleanup."""

import asyncio
import io
import json
import os
import struct
import sys
import tempfile
import threading
import time
import pytest

import native_host
from native_host import (
    NativeHostBridge,
    send_native_message,
    cleanup_ipc_endpoints,
    SOCKET_PATH,
    PORT_FILE,
    IS_WINDOWS,
)


def test_send_native_message_framing():
    """Test that send_native_message writes 4-byte LE length header + UTF-8 JSON payload."""
    fake_stdout = io.BytesIO()
    test_obj = {"action": "click", "refId": 42, "text": "Hello 🌐"}

    old_stdout = sys.stdout
    try:
        class BufferWrapper:
            buffer = fake_stdout
        sys.stdout = BufferWrapper()

        send_native_message(test_obj)

        raw = fake_stdout.getvalue()
        assert len(raw) >= 4
        length = struct.unpack("<I", raw[:4])[0]
        payload = raw[4:4 + length]
        assert len(payload) == length
        decoded = json.loads(payload.decode("utf-8"))
        assert decoded == test_obj
    finally:
        sys.stdout = old_stdout


def test_cleanup_ipc_endpoints_removes_files(tmp_path):
    """Test cleanup_ipc_endpoints safely unlinks socket/port file if present."""
    if IS_WINDOWS:
        test_file = PORT_FILE
    else:
        test_file = SOCKET_PATH

    # Create dummy endpoint file
    os.makedirs(os.path.dirname(test_file), exist_ok=True)
    if os.path.exists(test_file):
        try:
            os.unlink(test_file)
        except OSError:
            pass
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("dummy")
    assert os.path.exists(test_file)

    cleanup_ipc_endpoints()
    assert not os.path.exists(test_file)


@pytest.mark.asyncio
async def test_native_host_bridge_lifecycle_and_ipc_routing():
    """Test full async NativeHostBridge startup, client connection, and bi-directional message routing."""
    loop = asyncio.get_running_loop()
    bridge = NativeHostBridge(loop, auto_read_stdin=False)

    # Capture stdout messages
    captured_stdout = io.BytesIO()
    old_stdout = sys.stdout

    class BufferWrapper:
        buffer = captured_stdout

    sys.stdout = BufferWrapper()

    try:
        cleanup_ipc_endpoints()

        # Start server in background task
        server_task = asyncio.create_task(bridge.start())
        await asyncio.sleep(0.1)

        # Check that host_ready message was sent to stdout
        raw_out = captured_stdout.getvalue()
        assert len(raw_out) >= 4
        h_len = struct.unpack("<I", raw_out[:4])[0]
        h_msg = json.loads(raw_out[4:4 + h_len].decode("utf-8"))
        assert h_msg.get("event") == "host_ready"

        # Connect a mock client via Unix socket or TCP
        if IS_WINDOWS:
            with open(PORT_FILE, "r", encoding="utf-8") as f:
                port = int(f.read().strip())
            client_reader, client_writer = await asyncio.open_connection("127.0.0.1", port)
        else:
            client_reader, client_writer = await asyncio.open_unix_connection(SOCKET_PATH)

        # Client sends a request
        req = {"id": 101, "action": "navigate", "params": {"url": "https://example.com"}}
        client_writer.write((json.dumps(req) + "\n").encode("utf-8"))
        await client_writer.drain()
        await asyncio.sleep(0.05)

        # Check that request was forwarded to Chrome stdout
        current_out = captured_stdout.getvalue()
        # Find message with id=101
        offset = 4 + h_len
        req_len = struct.unpack("<I", current_out[offset:offset + 4])[0]
        req_payload = json.loads(current_out[offset + 4:offset + 4 + req_len].decode("utf-8"))
        assert req_payload["id"] == 101
        assert req_payload["action"] == "navigate"

        # Simulate Chrome sending response back on stdin queue
        chrome_resp = {"id": 101, "success": True, "result": {"title": "Example Domain"}}
        await bridge.msg_queue.put(json.dumps(chrome_resp).encode("utf-8"))

        # Client receives response
        resp_line = await asyncio.wait_for(client_reader.readline(), timeout=2.0)
        parsed_resp = json.loads(resp_line.decode("utf-8"))
        assert parsed_resp["id"] == 101
        assert parsed_resp["success"] is True
        assert parsed_resp["result"]["title"] == "Example Domain"

        # Test invalid JSON from client
        client_writer.write(b"not valid json\n")
        await client_writer.drain()
        err_line = await asyncio.wait_for(client_reader.readline(), timeout=2.0)
        parsed_err = json.loads(err_line.decode("utf-8"))
        assert parsed_err["success"] is False
        assert "Invalid JSON" in parsed_err["error"]

        client_writer.close()
        await client_writer.wait_closed()

        # Stop bridge by sending EOF on queue
        await bridge.msg_queue.put(None)
        await asyncio.wait_for(server_task, timeout=2.0)

    finally:
        bridge.shutdown()
        cleanup_ipc_endpoints()
        sys.stdout = old_stdout


@pytest.mark.asyncio
async def test_stdin_reader_thread_decodes_framed_stream():
    """Test _stdin_reader_thread parses length headers and puts messages on queue."""
    loop = asyncio.get_running_loop()

    msg1 = json.dumps({"action": "hello"}).encode("utf-8")
    msg2 = json.dumps({"action": "world"}).encode("utf-8")

    stream_data = struct.pack("<I", len(msg1)) + msg1 + struct.pack("<I", len(msg2)) + msg2
    fake_stdin = io.BytesIO(stream_data)

    bridge = NativeHostBridge(loop, stdin_stream=fake_stdin, auto_read_stdin=False)
    t = threading.Thread(target=bridge._stdin_reader_thread, daemon=True)
    t.start()
    t.join(timeout=1.0)

    received1 = await asyncio.wait_for(bridge.msg_queue.get(), timeout=1.0)
    assert received1 == msg1
    received2 = await asyncio.wait_for(bridge.msg_queue.get(), timeout=1.0)
    assert received2 == msg2
    eof = await asyncio.wait_for(bridge.msg_queue.get(), timeout=1.0)
    assert eof is None

