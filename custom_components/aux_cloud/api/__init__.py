"""Public API surface used by the AUX Cloud Home Assistant integration."""

from .client import AuxCloudAPI
from .errors import (
    AuxApiError,
    AuxAuthError,
    AuxDeviceError,
    AuxNetworkError,
    AuxRateLimitError,
    AuxServerError,
    AuxSessionExpired,
    AuxUnknownApiError,
    config_flow_error_key,
    issue_id_for_error,
)
from .protocol.websocket import extract_websocket_updates
from .transports.websocket import AuxWebSocketState

__all__ = [
    "AuxApiError",
    "AuxAuthError",
    "AuxCloudAPI",
    "AuxDeviceError",
    "AuxNetworkError",
    "AuxRateLimitError",
    "AuxServerError",
    "AuxSessionExpired",
    "AuxUnknownApiError",
    "AuxWebSocketState",
    "config_flow_error_key",
    "extract_websocket_updates",
    "issue_id_for_error",
]
