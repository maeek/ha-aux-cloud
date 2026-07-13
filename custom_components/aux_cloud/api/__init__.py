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
)
from .protocol.websocket import extract_websocket_updates

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
    "extract_websocket_updates",
]
