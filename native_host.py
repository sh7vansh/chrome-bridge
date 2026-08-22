#!/usr/bin/env python3
"""Chrome Bridge - Pure Python Native Messaging Host & Fast IPC Server Facade."""

import os
import sys
import tempfile

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from chrome_sdk import auto_bootstrap_environment
    auto_bootstrap_environment()
except ImportError:
    pass

from chrome_bridge.transport import (
    DEFAULT_PORT_FILE,
    DEFAULT_SOCKET_PATH,
    IpcFramingEngine,
    NativeHostBridge,
    NativeIpcServer,
    SOCKET_PATH,
    cleanup_ipc_endpoints,
    pending_requests,
    send_native_message,
)

IS_WINDOWS = sys.platform == "win32"
PORT_FILE = DEFAULT_PORT_FILE


def main() -> None:
    """CLI entrypoint for Chrome Bridge Native Host."""
    NativeIpcServer.run_main()


if __name__ == "__main__":
    main()

