"""HTTP control strategy for AUX Cloud."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ..errors import AuxServerError, raise_for_cloud_response
from ..protocol.common import (
    build_device_params_directive,
    device_values_to_params,
    parse_std_data,
)

_LOGGER = logging.getLogger(__name__)

RequestCallback = Callable[..., Awaitable[dict]]
HeadersCallback = Callable[..., dict]


class AuxCloudHttpStrategy:
    """HTTP device-control API used for bootstrap, polling, and fallback commands."""

    def __init__(
        self,
        make_request: RequestCallback,
        get_headers: HeadersCallback,
        license_token: str,
    ) -> None:
        """Initialize the HTTP strategy."""
        self._make_request = make_request
        self._get_headers = get_headers
        self._license_token = license_token

    async def get_device_params(
        self, device: dict, params: list[str] | None = None
    ) -> dict:
        """Query device parameters over HTTP."""
        if params is None:
            params = []
        return await self.act_device_params(device, "get", params)

    async def set_device_params(self, device: dict, values: dict[str, Any]) -> dict:
        """Set device parameters over HTTP."""
        params, vals = device_values_to_params(values)
        response = await self.act_device_params(device, "set", params, vals)
        return response or values

    async def act_device_params(
        self,
        device: dict,
        act: str,
        params: list[str] | None = None,
        vals: list | None = None,
    ) -> dict:
        """Query or set device parameters over HTTP."""
        directive = build_device_params_directive(device, act, params, vals)
        data = {"directive": directive}

        json_data = await self._make_request(
            method="POST",
            endpoint="device/control/v2/sdkcontrol",
            data=data,
            # Theoretically license in query param is not needed but
            # this follows the original app request.
            params={"license": self._license_token},
            headers=self._get_headers(),
        )

        _LOGGER.debug("AUX device parameter HTTP request completed")
        event = json_data.get("event")
        if not isinstance(event, dict):
            raise AuxServerError(
                "AUX device control response has no event",
                endpoint="device/control/v2/sdkcontrol",
            )
        return parse_control_event(event)


def parse_control_event(event: dict) -> dict:
    """Parse a KeyValueControl HTTP event response."""
    raise_for_cloud_response(event, endpoint="device/control/v2/sdkcontrol")

    if event.get("header", {}).get("name") != "Response":
        raise AuxServerError(
            "Unexpected AUX device control response",
            endpoint="device/control/v2/sdkcontrol",
        )

    payload = event.get("payload", {})
    if not isinstance(payload, dict):
        raise AuxServerError(
            "Invalid AUX device control payload",
            endpoint="device/control/v2/sdkcontrol",
        )
    data = payload.get("data")
    try:
        return parse_std_data(data)
    except (TypeError, ValueError) as exc:
        raise AuxServerError(
            "Invalid AUX device control data",
            endpoint="device/control/v2/sdkcontrol",
        ) from exc
