"""TransportClient Protocol, IpcFramingEngine, and ChromeSocketClient IPC transport adapter."""

import io
import json
import os
import socket
import struct
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, Union, runtime_checkable

from .exceptions import (
    DEFAULT_PORT_FILE,
    DEFAULT_SOCKET_PATH,
    SOCKET_PATH,
    BrowserUnavailableError,
    ChromeBridgeError,
    NavigationTimeoutError,
    decode_domain_error,
)


class IpcFramingEngine:
    """Consolidated binary length-prefixed and line-delimited message framing engine."""

    _stdout_lock = threading.Lock()

    @staticmethod
    def pack_length_prefixed(obj: Any) -> bytes:
        """Encode object as 4-byte little-endian length-prefixed JSON byte stream."""
        if isinstance(obj, (bytes, bytearray)):
            payload = bytes(obj)
        else:
            payload = json.dumps(obj).encode("utf-8")
        header = struct.pack("<I", len(payload))
        return header + payload

    @classmethod
    def write_native_message(cls, obj: Any, stream: Optional[Any] = None) -> None:
        """Atomically encode and write a 4-byte length-prefixed message to a binary stream."""
        target_stream = stream if stream is not None else sys.stdout.buffer
        packet = cls.pack_length_prefixed(obj)
        with cls._stdout_lock:
            target_stream.write(packet)
            target_stream.flush()

    @staticmethod
    def read_length_prefixed_bytes(stream: Any) -> Optional[bytes]:
        """Read 4-byte little-endian length header and read full payload bytes from stream."""
        try:
            header = stream.read(4)
            if not header or len(header) < 4:
                return None
            msg_len = struct.unpack("<I", header)[0]
            if msg_len == 0:
                return b""
            payload = bytearray()
            while len(payload) < msg_len:
                chunk = stream.read(msg_len - len(payload))
                if not chunk:
                    return None
                payload.extend(chunk)
            if len(payload) < msg_len:
                return None
            return bytes(payload)
        except Exception:
            return None

    @classmethod
    def unpack_length_prefixed_stream(cls, stream: Any) -> Optional[Dict[str, Any]]:
        """Read 4-byte little-endian length header and decode full JSON payload from a stream."""
        try:
            raw_bytes = cls.read_length_prefixed_bytes(stream)
            if raw_bytes is None:
                return None
            if len(raw_bytes) == 0:
                return {}
            return json.loads(raw_bytes.decode("utf-8", errors="replace"))
        except Exception:
            return None

    @staticmethod
    def pack_line_delimited(obj: Any) -> bytes:
        """Encode object as newline-terminated JSON bytes."""
        if isinstance(obj, str):
            payload = obj if obj.endswith("\n") else obj + "\n"
            return payload.encode("utf-8")
        return json.dumps(obj).encode("utf-8") + b"\n"

    @staticmethod
    def unpack_line_delimited_buffer(buffer: bytes, on_error: str = "ignore") -> Tuple[List[Dict[str, Any]], bytes]:
        """Extract all complete newline-delimited JSON objects from buffer and return remainder."""
        messages: List[Dict[str, Any]] = []
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            line_str = line.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue
            try:
                msg = json.loads(line_str)
                if isinstance(msg, dict):
                    messages.append(msg)
                else:
                    messages.append({"value": msg})
            except Exception:
                if on_error == "error_dict":
                    messages.append({"__parse_error__": True, "raw": line_str})
        return messages, buffer


@runtime_checkable
class TransportClient(Protocol):
    """Protocol seam for Chrome Bridge IPC transport adapters."""

    def call(self, action: str, params: Optional[Dict[str, Any]] = None, timeout: float = 15.0) -> Any:
        """Send action request and return structured response or raise transport/domain exception."""
        ...

    def connect(self, retries: int = 5, backoff: float = 0.2) -> None:
        """Establish transport connection."""
        ...

    def close(self) -> None:
        """Close transport connection."""
        ...


class InProcessTransportClient:
    """In-memory TransportClient adapter for fast in-process testing and mock execution.

    Allows executing against an in-process mock handler or stateful test dispatcher
    without spawning background processes or opening OS sockets.
    """

    def __init__(
        self,
        handler: Optional[Callable[[str, Optional[Dict[str, Any]]], Any]] = None,
        auto_snapshot: Optional[str] = None,
    ):
        self.handler = handler
        self.auto_snapshot = auto_snapshot
        self.connected = False
        self.calls: List[Tuple[str, Optional[Dict[str, Any]]]] = []

    def connect(self, retries: int = 5, backoff: float = 0.2) -> None:
        """Establish in-memory transport connection."""
        self.connected = True

    def close(self) -> None:
        """Close in-memory transport connection."""
        self.connected = False

    def call(self, action: str, params: Optional[Dict[str, Any]] = None, timeout: float = 15.0) -> Any:
        """Dispatch action to in-process handler with error decoding."""
        self.connected = True
        self.calls.append((action, params))

        if self.handler is None:
            if action == "list_tabs":
                return [{"id": 1, "title": "In-Process Tab", "url": "https://example.com", "active": True}]
            if action == "get_active_tab":
                return {"id": 1, "title": "In-Process Tab", "url": "https://example.com", "active": True}
            if action == "get_page_content":
                return {"snapshot": 'PAGE: "In-Process Tab"\n- button [#1] "Submit"'}
            if action == "find_element":
                q = params.get("query", "element") if params else "element"
                return {"selector": '[data-cbridge-id="cb_1_inproc"]', "tagName": "button", "role": "button", "text": str(q)}
            if action == "query_elements":
                return [{"selector": '[data-cbridge-id="cb_1_inproc"]', "tagName": "button", "role": "button", "text": "Item 1"}]
            return {"status": "ok", "action": action}

        resp = self.handler(action, params)
        if isinstance(resp, dict):
            if resp.get("success") is False or "error" in resp:
                decode_domain_error(
                    err_data=resp.get("error"),
                    params=params,
                    auto_snapshot=resp.get("auto_snapshot", self.auto_snapshot),
                )
            if "result" in resp and "success" in resp:
                return resp["result"]
        return resp


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
        data = IpcFramingEngine.pack_line_delimited(req_payload)

        try:
            assert self._sock is not None
            self._sock.settimeout(timeout)
            self._sock.sendall(data)

            while True:
                # Use IpcFramingEngine to unpack messages from buffer
                messages, self._buffer = IpcFramingEngine.unpack_line_delimited_buffer(self._buffer)
                for resp in messages:
                    if resp.get("id") == req_id:
                        if not resp.get("success", False):
                            decode_domain_error(
                                err_data=resp.get("error"),
                                params=params,
                                auto_snapshot=resp.get("auto_snapshot"),
                            )
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
        """Legacy helper for backward compatibility; delegates to decode_domain_error."""
        decode_domain_error(
            err_data=resp.get("error"),
            params=params,
            auto_snapshot=resp.get("auto_snapshot"),
        )


# Global map of pending client requests: request_id -> asyncio.StreamWriter
pending_requests: Dict[int, Any] = {}


def send_native_message(obj: dict, stream: Optional[Any] = None) -> None:
    """Encode and write a 4-byte little-endian length-prefixed JSON message to Chrome stdout."""
    try:
        IpcFramingEngine.write_native_message(obj, stream=stream)
    except Exception:
        # Chrome pipe may have closed
        pass


def cleanup_ipc_endpoints(socket_path: str = SOCKET_PATH, port_file: Optional[str] = None) -> None:
    """Remove temporary socket or port file on host exit."""
    target_port = port_file if port_file is not None else DEFAULT_PORT_FILE
    try:
        if sys.platform == "win32" or os.name == "nt":
            if os.path.exists(target_port):
                os.remove(target_port)
        else:
            if os.path.exists(socket_path):
                os.remove(socket_path)
    except Exception:
        pass


class NativeIpcServer:
    """Manages stdio communication with Chrome and local IPC server for AI clients."""

    def __init__(
        self,
        loop: Any,
        stdin_stream: Optional[Any] = None,
        auto_read_stdin: bool = True,
        socket_path: str = SOCKET_PATH,
        port_file: Optional[str] = None,
    ):
        import asyncio
        self.loop = loop
        self.stdin_stream = stdin_stream if stdin_stream is not None else sys.stdin.buffer
        self.auto_read_stdin = auto_read_stdin
        self.socket_path = socket_path
        self.port_file = port_file if port_file is not None else DEFAULT_PORT_FILE
        self.msg_queue: asyncio.Queue[Optional[Any]] = asyncio.Queue()
        self.stop_event = threading.Event()
        self.server: Optional[Any] = None
        self._reader_thread: Optional[threading.Thread] = None

    def _stdin_reader_thread(self) -> None:
        """Background thread reading length-prefixed messages from Chrome stdin."""
        stdin = self.stdin_stream
        while not self.stop_event.is_set():
            payload = IpcFramingEngine.read_length_prefixed_bytes(stdin)
            if payload is None:
                break
            self.loop.call_soon_threadsafe(self.msg_queue.put_nowait, payload)

        # Signal EOF to asyncio loop
        self.loop.call_soon_threadsafe(self.msg_queue.put_nowait, None)

    async def _handle_chrome_messages(self) -> None:
        """Process messages received from Chrome and route responses to waiting clients."""
        while True:
            item = await self.msg_queue.get()
            if item is None:
                # Chrome closed stdin
                break

            try:
                if isinstance(item, (bytes, bytearray)):
                    msg_str = item.decode("utf-8", errors="replace")
                    response = json.loads(msg_str)
                else:
                    response = item

                req_id = response.get("id")

                if req_id is not None and req_id in pending_requests:
                    writer = pending_requests.pop(req_id)
                    try:
                        if not writer.is_closing():
                            writer.write((json.dumps(response) + "\n").encode("utf-8"))
                            await writer.drain()
                    except Exception:
                        pass
            except Exception:
                pass

        # If Chrome stdin closed, shut down server
        self.shutdown()

    async def handle_client_connection(self, reader: Any, writer: Any) -> None:
        """Handle incoming connection from an MCP or Python SDK client."""
        client_buffer = b""
        try:
            while not self.stop_event.is_set():
                chunk = await reader.read(65536)
                if not chunk:
                    break
                client_buffer += chunk

                messages, client_buffer = IpcFramingEngine.unpack_line_delimited_buffer(client_buffer, on_error="error_dict")
                for req in messages:
                    if req.get("__parse_error__"):
                        err_resp = {"success": False, "error": "Invalid JSON request"}
                        writer.write((json.dumps(err_resp) + "\n").encode("utf-8"))
                        await writer.drain()
                        continue
                    req_id = req.get("id")
                    if req_id is not None:
                        pending_requests[req_id] = writer
                        send_native_message(req)
        except Exception:
            pass
        finally:
            # Clean up pending requests registered by this writer
            for r_id, w in list(pending_requests.items()):
                if w is writer:
                    pending_requests.pop(r_id, None)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self) -> None:
        """Start the IPC server and Chrome message dispatch loop."""
        import asyncio
        cleanup_ipc_endpoints(self.socket_path, self.port_file)

        is_win = sys.platform == "win32" or os.name == "nt"

        if is_win:
            self.server = await asyncio.start_server(
                self.handle_client_connection,
                host="127.0.0.1",
                port=0,
            )
            sockets = self.server.sockets
            if sockets:
                port = sockets[0].getsockname()[1]
                with open(self.port_file, "w", encoding="utf-8") as f:
                    f.write(str(port))
                send_native_message({"event": "host_ready", "port": port})
        else:
            self.server = await asyncio.start_unix_server(
                self.handle_client_connection,
                path=self.socket_path,
            )
            send_native_message({"event": "host_ready", "socketPath": self.socket_path})

        # Start background thread for stdin reading if enabled
        if self.auto_read_stdin:
            self._reader_thread = threading.Thread(target=self._stdin_reader_thread, daemon=True)
            self._reader_thread.start()

        # Run Chrome message processing
        await self._handle_chrome_messages()

    def shutdown(self) -> None:
        """Gracefully shut down the bridge."""
        self.stop_event.set()
        if self.server:
            self.server.close()
        cleanup_ipc_endpoints(self.socket_path, self.port_file)

    @classmethod
    def run_main(cls) -> None:
        """CLI entrypoint for Chrome Bridge Native Host."""
        import asyncio
        import atexit
        import signal

        # Ensure unbuffered binary I/O for stdio framing on Windows
        if sys.platform == "win32":
            try:
                import msvcrt
                msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
                msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
            except Exception:
                pass

        atexit.register(cleanup_ipc_endpoints)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        bridge = cls(loop)

        def _signal_handler(*args: Any) -> None:
            bridge.shutdown()
            cleanup_ipc_endpoints()
            sys.exit(0)

        try:
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)
        except Exception:
            pass

        try:
            loop.run_until_complete(bridge.start())
        except KeyboardInterrupt:
            pass
        finally:
            bridge.shutdown()
            cleanup_ipc_endpoints()


# Backward-compatible alias
NativeHostBridge = NativeIpcServer

