"""AUX Cloud command orchestration."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from ..devices.profiles import prepare_command
from .errors import raise_for_cloud_response
from .protocol.common import build_device_params_directive, device_values_to_params
from .protocol.websocket import extract_websocket_updates
from .transports.http import AuxCloudHttpStrategy

_LOGGER = logging.getLogger(__name__)


class AuxCloudWebSocketStrategy:
    """WebSocket device-control strategy."""

    def __init__(
        self,
        websocket_getter: Callable[[], Any],
        app_header_factory: Callable[[str | None], dict],
    ) -> None:
        """Initialize the websocket strategy."""
        self._websocket_getter = websocket_getter
        self._app_header_factory = app_header_factory

    @property
    def connected(self) -> bool:
        """Return whether the websocket transport is ready for commands."""
        websocket = self._websocket_getter()
        return websocket is not None and websocket.connected

    async def act_device_params(
        self,
        device: dict,
        act: str,
        params: list[str] | None = None,
        vals: list | None = None,
    ) -> dict:
        """Query or set device parameters over websocket."""
        websocket = self._websocket_getter()
        if websocket is None or not websocket.connected:
            raise ConnectionError("WebSocket is not connected")

        directive = build_device_params_directive(device, act, params, vals)
        response = await websocket.async_send_opencontrol(
            {
                "bodyList": [{"directive": directive}],
                "header": self._app_header_factory(device.get("familyId")),
            }
        )
        raise_for_cloud_response(response, endpoint="websocket/transit.opencontrol")
        status = response.get("status")
        if status not in (None, 0, "0"):
            raise ValueError(f"WebSocket control failed: {response}")

        updates = extract_websocket_updates(response)
        for update in updates:
            if update["endpointId"] == device["endpointId"]:
                return update["params"]

        return {}


class AuxCloudControlService:
    """WebSocket-first command facade with HTTP fallback."""

    def __init__(
        self,
        http_strategy: AuxCloudHttpStrategy,
        websocket_strategy: AuxCloudWebSocketStrategy,
    ) -> None:
        """Initialize the control service."""
        self.http_strategy = http_strategy
        self.websocket_strategy = websocket_strategy

    async def get_device_params(
        self, device: dict, params: list[str] | None = None
    ) -> dict:
        """Query device parameters over HTTP."""
        return await self.http_strategy.get_device_params(device, params)

    async def set_device_params(self, device: dict, values: dict[str, Any]) -> dict:
        """Set device parameters, preferring websocket and falling back to HTTP."""
        params, vals = device_values_to_params(values)
        params, vals = prepare_command(device, "set", params, vals)

        try:
            if self.websocket_strategy.connected:
                response = await self.websocket_strategy.act_device_params(
                    device, "set", params, vals
                )
                return response or values
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning(
                "AUX Cloud websocket command failed for %s, falling back to HTTP: %s",
                device.get("endpointId"),
                exc,
            )

        response = await self.http_strategy.act_device_params(
            device, "set", params, vals
        )
        return response or values
