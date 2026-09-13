"""Public API surface used by the AUX Cloud Home Assistant integration."""

from collections.abc import Callable
from typing import Any, Protocol

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
from .models import AuxCredentials, AuxDevice, DeviceUpdate, InventorySnapshot


class AuxCloudClient(Protocol):
    """Replaceable AUX cloud client used by the Home Assistant adapter."""

    @property
    def user_id(self) -> str | None:
        """Return the authenticated cloud user ID."""

    def is_logged_in(self) -> bool:
        """Return whether the client has an active identity."""

    async def login(self, credentials: AuxCredentials) -> None:
        """Authenticate with the cloud service."""

    async def scan_devices(self) -> InventorySnapshot:
        """Return one account-wide device inventory scan."""

    async def set_device_params(
        self, device: AuxDevice, values: dict[str, Any]
    ) -> dict[str, Any]:
        """Set device parameters using the best available transport."""

    async def run_realtime(
        self,
        devices: list[AuxDevice] | None = None,
        listener: Callable[[tuple[DeviceUpdate, ...]], None] | None = None,
        connection_listener: Callable[[bool], None] | None = None,
    ) -> None:
        """Supervise realtime updates until cancelled."""

    async def update_realtime_devices(self, devices: list[AuxDevice]) -> None:
        """Update active relay subscriptions."""

    async def close(self) -> None:
        """Close resources owned by the client."""


__all__ = [
    "AuxApiError",
    "AuxAuthError",
    "AuxCloudClient",
    "AuxCredentials",
    "AuxDevice",
    "AuxDeviceError",
    "AuxNetworkError",
    "AuxRateLimitError",
    "AuxServerError",
    "AuxSessionExpired",
    "AuxUnknownApiError",
    "DeviceUpdate",
    "InventorySnapshot",
]
