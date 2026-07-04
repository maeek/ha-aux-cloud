"""HTTP control strategy for AUX Cloud."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import Any

from ..errors import raise_for_cloud_response
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
            ssl=False,
        )

        _LOGGER.debug("Device params HTTP response: %s", json_data)
        try:
            return parse_control_event(json_data["event"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Failed to query device state: {data}, {json_data}"
            ) from exc


def parse_control_event(event: dict) -> dict:
    """Parse a KeyValueControl HTTP event response."""
    raise_for_cloud_response(event, endpoint="device/control/v2/sdkcontrol")

    if event.get("header", {}).get("name") != "Response":
        raise ValueError("Unexpected control response")

    payload = event.get("payload", {})
    status = payload.get("status")
    data = payload.get("data")
    if status not in (None, 0) and not data:
        raise ValueError(f"Control response status {status}")

    return parse_std_data(data)
