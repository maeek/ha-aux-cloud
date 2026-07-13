"""AUX Cloud device-control boundary."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol

from ..devices.profiles import get_product_profile
from .errors import (
    AuxDeviceError,
    AuxNetworkError,
    AuxServerError,
    AuxUnknownApiError,
)
from .models import AuxDevice
from .protocol.common import (
    build_device_params_directive,
    device_values_to_params,
    parse_control_event,
)
from .protocol.websocket import (
    extract_websocket_updates,
    validate_websocket_response,
)
from .session import LICENSE, AuxCloudSession

_LOGGER = logging.getLogger(__name__)
_CONTROL_ENDPOINT = "device/control/v2/sdkcontrol"


class WebSocketControl(Protocol):
    """Minimal websocket contract needed for device commands."""

    @property
    def connected(self) -> bool:
        """Return whether commands can be sent."""

    async def async_send_opencontrol(
        self, data: dict[str, Any], *, timeout: int = 10
    ) -> dict[str, Any]:
        """Send a control directive and return its acknowledgement."""


class AuxCloudControl:
    """HTTP control client with an optional websocket fast path."""

    def __init__(
        self,
        session: AuxCloudSession,
        websocket_getter: Callable[[], WebSocketControl | None],
        app_header_factory: Callable[[str | None], dict[str, Any]],
    ) -> None:
        """Initialize the control boundary."""
        self._session = session
        self._websocket_getter = websocket_getter
        self._app_header_factory = app_header_factory

    async def get_device_params(
        self, device: AuxDevice, params: list[str] | None = None
    ) -> dict[str, Any]:
        """Query parameters over HTTP."""
        return await self._act_http(device, "get", params or [])

    async def set_device_params(
        self, device: AuxDevice, values: dict[str, Any]
    ) -> dict[str, Any]:
        """Set parameters over websocket, falling back for relay failures."""
        params, vals = self._prepare_set(device, values)
        websocket = self._websocket_getter()
        try:
            if websocket is not None and websocket.connected:
                response = await self._act_websocket(websocket, device, params, vals)
                return response or values
        except (
            ConnectionError,
            TimeoutError,
            AuxNetworkError,
            AuxServerError,
            AuxUnknownApiError,
        ) as exc:
            _LOGGER.debug(
                "AUX websocket command failed; using HTTP (%s)",
                type(exc).__name__,
            )
        return await self.set_device_params_http(device, values, params, vals)

    async def set_device_params_http(
        self,
        device: AuxDevice,
        values: dict[str, Any],
        params: list[str] | None = None,
        vals: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Set parameters over HTTP after validation or session recovery."""
        if params is None or vals is None:
            params, vals = self._prepare_set(device, values)
        response = await self._act_http(device, "set", params, vals)
        return response or values

    @staticmethod
    def _prepare_set(
        device: AuxDevice, values: dict[str, Any]
    ) -> tuple[list[str], list[Any]]:
        profile = get_product_profile(device.get("productId"))
        if invalid_param := profile.invalid_command_parameter(values):
            raise AuxDeviceError(
                f"AUX product does not support setting {invalid_param}",
                endpoint=_CONTROL_ENDPOINT,
            )
        params, vals = device_values_to_params(values)
        return profile.prepare_command(device, params, vals)

    async def _act_websocket(
        self,
        websocket: WebSocketControl,
        device: AuxDevice,
        params: list[str],
        vals: list[Any],
    ) -> dict[str, Any]:
        directive = build_device_params_directive(device, "set", params, vals)
        response = await websocket.async_send_opencontrol(
            {
                "bodyList": [{"directive": directive}],
                "header": self._app_header_factory(device.get("familyId")),
            }
        )
        validate_websocket_response(response, endpoint="websocket/transit.opencontrol")
        for update in extract_websocket_updates(response):
            if update.endpoint_id == device["endpointId"]:
                return dict(update.params)
        return {}

    async def _act_http(
        self,
        device: AuxDevice,
        act: str,
        params: list[str],
        vals: list[Any] | None = None,
    ) -> dict[str, Any]:
        directive = build_device_params_directive(device, act, params, vals)
        json_data = await self._session.make_request(
            _CONTROL_ENDPOINT,
            data={"directive": directive},
            params={"license": LICENSE},
        )
        event = json_data.get("event")
        if not isinstance(event, dict):
            raise AuxServerError(
                "AUX device control response has no event",
                endpoint=_CONTROL_ENDPOINT,
            )
        return parse_control_event(event)
