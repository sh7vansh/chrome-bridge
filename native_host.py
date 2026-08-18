#!/usr/bin/env python3
"""Chrome Bridge - Pure Python Native Messaging Host & Fast IPC Server.

Standard library only. Delivers < 5ms startup latency and bridges Chrome Native
Messaging stdio pipes with a local Unix domain socket (POSIX) or dynamic TCP
localhost socket (Windows) for MCP and Python REPL clients.
"""

import asyncio
import atexit
import io
import json
import os
import signal
import struct
import sys
import tempfile
import threading
from typing import Dict, Optional

# Ensure unbuffered binary I/O for stdio framing
if sys.platform == "win32":
    import msvcrt
    try:
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    except Exception:
        pass

IS_WINDOWS = sys.platform == "win32"
SOCKET_PATH = os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.sock")
PORT_FILE = os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.port")

# Map of pending client requests: request_id -> asyncio.StreamWriter
pending_requests: Dict[int, asyncio.StreamWriter] = {}
_stdout_lock = threading.Lock()


def send_native_message(obj: dict) -> None:
    """Encode and write a 4-byte little-endian length-prefixed JSON message to Chrome stdout."""
    try:
        payload = json.dumps(obj).encode("utf-8")
        header = struct.pack("<I", len(payload))
        with _stdout_lock:
            sys.stdout.buffer.write(header + payload)
            sys.stdout.buffer.flush()
    except Exception:
        # Chrome pipe may have closed
        pass


def cleanup_ipc_endpoints() -> None:
    """Remove temporary socket or port file on host exit."""
    try:
        if IS_WINDOWS:
            if os.path.exists(PORT_FILE):
                os.remove(PORT_FILE)
        else:
            if os.path.exists(SOCKET_PATH):
                os.remove(SOCKET_PATH)
    except Exception:
        pass


class NativeHostBridge:
    """Manages stdio communication with Chrome and local IPC server for AI clients."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        stdin_stream: Optional[io.BufferedIOBase] = None,
        auto_read_stdin: bool = True,
    ):
        self.loop = loop
        self.stdin_stream = stdin_stream if stdin_stream is not None else sys.stdin.buffer
        self.auto_read_stdin = auto_read_stdin
        self.msg_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self.stop_event = threading.Event()
        self.server: Optional[asyncio.AbstractServer] = None
        self._reader_thread: Optional[threading.Thread] = None

    def _stdin_reader_thread(self) -> None:
        """Background thread reading length-prefixed messages from Chrome stdin."""
        stdin = self.stdin_stream
        while not self.stop_event.is_set():
            try:
                header = stdin.read(4)
                if not header or len(header) < 4:
                    break  # EOF reached
                msg_len = struct.unpack("<I", header)[0]
                if msg_len == 0:
                    continue
                payload = bytearray()
                while len(payload) < msg_len:
                    chunk = stdin.read(msg_len - len(payload))
                    if not chunk:
                        break
                    payload.extend(chunk)
                if len(payload) < msg_len:
                    break

                self.loop.call_soon_threadsafe(self.msg_queue.put_nowait, bytes(payload))
            except Exception:
                break

        # Signal EOF to asyncio loop
        self.loop.call_soon_threadsafe(self.msg_queue.put_nowait, None)

    async def _handle_chrome_messages(self) -> None:
        """Process messages received from Chrome and route responses to waiting clients."""
        while True:
            payload = await self.msg_queue.get()
            if payload is None:
                # Chrome closed stdin
                break

            try:
                msg_str = payload.decode("utf-8", errors="replace")
                response = json.loads(msg_str)
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

    async def handle_client_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle incoming connection from an MCP or Python SDK client."""
        client_buffer = ""
        try:
            while not self.stop_event.is_set():
                chunk = await reader.read(65536)
                if not chunk:
                    break
                client_buffer += chunk.decode("utf-8", errors="replace")

                lines = client_buffer.split("\n")
                client_buffer = lines.pop()  # Keep trailing fragment

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        req = json.loads(line)
                        req_id = req.get("id")
                        if req_id is not None:
                            pending_requests[req_id] = writer
                            send_native_message(req)
                    except Exception:
                        err_resp = {"success": False, "error": "Invalid JSON request"}
                        writer.write((json.dumps(err_resp) + "\n").encode("utf-8"))
                        await writer.drain()
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
        cleanup_ipc_endpoints()

        if IS_WINDOWS:
            self.server = await asyncio.start_server(
                self.handle_client_connection,
                host="127.0.0.1",
                port=0,
            )
            sockets = self.server.sockets
            if sockets:
                port = sockets[0].getsockname()[1]
                with open(PORT_FILE, "w", encoding="utf-8") as f:
                    f.write(str(port))
                send_native_message({"event": "host_ready", "port": port})
        else:
            self.server = await asyncio.start_unix_server(
                self.handle_client_connection,
                path=SOCKET_PATH,
            )
            send_native_message({"event": "host_ready", "socketPath": SOCKET_PATH})

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
        cleanup_ipc_endpoints()


def main() -> None:
    """CLI entrypoint for Chrome Bridge Native Host."""
    atexit.register(cleanup_ipc_endpoints)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bridge = NativeHostBridge(loop)

    def _signal_handler(*args) -> None:
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


if __name__ == "__main__":
    main()
