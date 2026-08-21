"""Chrome Bridge - Core Python Automation Subsystems."""

from .exceptions import (
    CRITICAL_DELETION_REGEX,
    CRITICAL_DELETION_TERMS,
    DEFAULT_BROWSER_UNAVAILABLE_MSG,
    DEFAULT_PORT_FILE,
    DEFAULT_SOCKET_PATH,
    SOCKET_PATH,
    SSO_ALLOWLIST,
    ActionInterceptionError,
    BrowserUnavailableError,
    ChromeBridgeError,
    ElementNotFoundError,
    NavigationTimeoutError,
    RunawayLoopDetectedError,
    SecurityException,
    TargetLocator,
    _extract_hostname,
    _format_ref_id,
    normalize_locator,
)
from .security import (
    ActionTracker,
    ChromeBridgeWorkerTelemetry,
    SafetyController,
    SecurityGateway,
    defang_telemetry_payload,
    global_safety,
    wrap_untrusted_data,
)
from .transport import (
    ChromeSocketClient,
    TransportClient,
)
from .compiler import (
    DomBatchSynthesizer,
    DomCompiler,
)

__all__ = [
    "ChromeBridgeError",
    "SecurityException",
    "RunawayLoopDetectedError",
    "BrowserUnavailableError",
    "ElementNotFoundError",
    "ActionInterceptionError",
    "NavigationTimeoutError",
    "TargetLocator",
    "normalize_locator",
    "CRITICAL_DELETION_TERMS",
    "CRITICAL_DELETION_REGEX",
    "SSO_ALLOWLIST",
    "DEFAULT_SOCKET_PATH",
    "DEFAULT_PORT_FILE",
    "SOCKET_PATH",
    "DEFAULT_BROWSER_UNAVAILABLE_MSG",
    "SecurityGateway",
    "SafetyController",
    "ActionTracker",
    "ChromeBridgeWorkerTelemetry",
    "wrap_untrusted_data",
    "defang_telemetry_payload",
    "global_safety",
    "TransportClient",
    "ChromeSocketClient",
    "DomCompiler",
    "DomBatchSynthesizer",
]
