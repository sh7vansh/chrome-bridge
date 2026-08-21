"""TransportClient Protocol, IpcFramingEngine, and ChromeSocketClient IPC transport adapter."""

import io
import json
import os
import socket
import struct
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union, runtime_checkable

from .exceptions import (
    DEFAULT_PORT_FILE,
    DEFAULT_SOCKET_PATH,
    SOCKET_PATH,
    BrowserUnavailableError,
    ChromeBridgeError,
    NavigationTimeoutError,
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
                            from .compiler import DomCompiler
                            DomCompiler.decode_error(
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
        """Legacy helper for backward compatibility; delegates to DomCompiler."""
        from .compiler import DomCompiler
        DomCompiler.decode_error(
            err_data=resp.get("error"),
            params=params,
            auto_snapshot=resp.get("auto_snapshot"),
        )
