"""TransportClient Protocol and ChromeSocketClient IPC transport adapter."""

import json
import os
import socket
import sys
import time
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from .exceptions import (
    DEFAULT_PORT_FILE,
    DEFAULT_SOCKET_PATH,
    SOCKET_PATH,
    BrowserUnavailableError,
    ChromeBridgeError,
    NavigationTimeoutError,
)


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
                            # Decode structured error into domain exception
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
