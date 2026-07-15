"""BroadLink DNA implementation of the AUX cloud client contract."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from typing import Any

import aiohttp

from ..api.errors import (
    AuxApiError,
    AuxAuthError,
    AuxDeviceError,
    AuxNetworkError,
    AuxRateLimitError,
    AuxServerError,
    AuxSessionExpired,
    AuxUnknownApiError,
)
from ..api.models import AuxCredentials, AuxDevice, DeviceUpdate, InventorySnapshot
from ..devices import get_device_profile
from .codec import (
    build_device_params_directive,
    device_values_to_params,
    extract_websocket_updates,
    parse_control_event,
    validate_websocket_response,
)
from .http import (
    COMPANY_ID,
    LICENSE,
    LICENSE_ID,
    DnaHttp,
)
from .inventory import DeviceInventory
from .websocket import (
    DnaWebSocket,
    websocket_origin,
)

_LOGGER = logging.getLogger(__name__)
_CONTROL_ENDPOINT = "device/control/v2/sdkcontrol"
_RETRY_INITIAL_DELAY = 5
_RETRY_MAX_DELAY = 60


class DnaClient:
    """Stable facade for interacting with AUX Cloud services."""

    def __init__(self, region: str, session: aiohttp.ClientSession) -> None:
        """Initialize the AUX Cloud facade."""
        self._session = DnaHttp(region=region, session=session)
        self._websocket: DnaWebSocket | None = None
        self._inventory = DeviceInventory(self._session, self)

    @property
    def user_id(self) -> str | None:
        """Return the cloud user ID."""
        return self._session.userid

    async def login(self, credentials: AuxCredentials) -> None:
        """Login to AUX Cloud services."""
        await self._session.login(credentials)

    def is_logged_in(self) -> bool:
        """Check if the user is logged in."""
        return self._session.is_logged_in()

    async def get_families(self) -> list[dict[str, Any]]:
        """List families associated with the user."""
        return await self._inventory.get_families()

    async def get_devices(
        self,
        familyid: str,
        shared: bool = False,
    ) -> list[AuxDevice]:
        """List devices associated with a family."""
        return await self._inventory.get_devices(familyid, shared)

    async def scan_devices(self) -> InventorySnapshot:
        """Fetch every personal and shared device for the account."""
        families = await self.get_families()
        results = await asyncio.gather(
            *(
                self.get_devices(family["familyid"], shared=shared)
                for family in families
                for shared in (False, True)
            ),
            return_exceptions=True,
        )
        devices: list[AuxDevice] = []
        errors: list[BaseException] = []
        for result in results:
            if isinstance(result, BaseException):
                if isinstance(result, asyncio.CancelledError):
                    raise result
                errors.append(result)
                continue
            for device in result:
                if isinstance(device, BaseException):
                    errors.append(device)
                else:
                    devices.append(device)
        devices = _deduplicate_devices(devices)
        if not devices and errors:
            raise _preferred_query_error(errors)
        return InventorySnapshot(tuple(devices), complete=not errors)

    def _get_app_header(self, family_id: str | None = None) -> dict[str, Any]:
        """Return the app relay header used inside transit.opencontrol."""
        return {
            "familyId": family_id or "",
            "language": "en",
            "licenseid": LICENSE_ID,
            "loginsession": self._session.loginsession or "",
            "userid": self._session.userid or "",
        }

    async def set_device_params(
        self, device: AuxDevice, values: dict[str, Any]
    ) -> dict[str, Any]:
        """Set device parameters, preferring websocket and falling back to HTTP."""
        expired_session = self._session.loginsession
        try:
            params, vals = self._prepare_set(device, values)
            try:
                if self._websocket is not None and self._websocket.connected:
                    response = await self._act_websocket(
                        self._websocket, device, params, vals
                    )
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
        except AuxSessionExpired:
            await self.close()
            await self._session.recover_session(expired_session=expired_session)
            return await self.set_device_params_http(device, values)

    async def get_device_params(
        self, device: AuxDevice, params: list[str] | None = None
    ) -> dict[str, Any]:
        """Query device parameters over HTTP."""
        return await self._act_http(device, "get", params or [])

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
        profile = get_device_profile(device)
        if invalid_param := profile.invalid_command_parameter(values):
            raise AuxDeviceError(
                f"AUX product does not support setting {invalid_param}",
                endpoint=_CONTROL_ENDPOINT,
            )
        params, vals = device_values_to_params(values)
        return profile.prepare_command(device, params, vals)

    async def _act_websocket(
        self,
        websocket: DnaWebSocket,
        device: AuxDevice,
        params: list[str],
        vals: list[Any],
    ) -> dict[str, Any]:
        directive = build_device_params_directive(device, "set", params, vals)
        response = await websocket.async_send_opencontrol(
            {
                "bodyList": [{"directive": directive}],
                "header": self._get_app_header(device.get("familyId")),
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

    async def get_websocket_urls(self) -> list[str]:
        """Get websocket relay URLs from the cloud."""
        json_data = await self._session.make_request(
            endpoint="appsync/apprelay/geturl",
        )
        urls = json_data.get("data", {}).get("url", [])
        return urls if json_data.get("status") == 0 and urls else []

    def _build_websocket_client(
        self, websocket_url: str, devices: list[AuxDevice] | None
    ) -> DnaWebSocket:
        """Build a websocket transport for the selected relay URL."""
        if self._session.loginsession is None or self._session.userid is None:
            raise AuxSessionExpired("AUX Cloud websocket authentication is missing")
        origin = websocket_origin(websocket_url) or self._session.url
        return DnaWebSocket(
            websocket_url=websocket_url,
            headers=self._session.get_headers(
                CompanyId=COMPANY_ID,
                Origin=origin,
                licenseid=LICENSE_ID,
            ),
            loginsession=self._session.loginsession,
            userid=self._session.userid,
            session=self._session.websession,
            devices=devices,
        )

    async def _run_websocket_once(
        self,
        devices: list[AuxDevice] | None = None,
        listener: Callable[[tuple[DeviceUpdate, ...]], None] | None = None,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        """Run one WebSocket connection attempt for real-time updates."""
        if not self.is_logged_in():
            raise AuxApiError("Cannot run WebSocket without being logged in.")

        urls = await self.get_websocket_urls()
        if not urls:
            raise AuxApiError("No AUX Cloud websocket relay URL available.")

        expired_session = self._session.loginsession
        for websocket_url in urls:
            reached_ready = False

            def ready() -> None:
                nonlocal reached_ready
                reached_ready = True
                if on_ready is not None:
                    on_ready()

            self._websocket = self._build_websocket_client(
                websocket_url.rstrip("/"), devices
            )
            try:
                await self._websocket.async_run(listener, ready)
                return
            except AuxSessionExpired:
                await self._session.recover_session(expired_session=expired_session)
                raise
            except AuxApiError:
                if reached_ready or websocket_url == urls[-1]:
                    raise
            finally:
                self._websocket = None

    async def run_realtime(
        self,
        devices: list[AuxDevice] | None = None,
        listener: Callable[[tuple[DeviceUpdate, ...]], None] | None = None,
        connection_listener: Callable[[bool], None] | None = None,
    ) -> None:
        """Reconnect the account relay until cancelled."""
        retry_delay = _RETRY_INITIAL_DELAY
        while True:
            reached_ready = False
            retry_after: int | None = None

            def ready() -> None:
                nonlocal reached_ready, retry_delay
                reached_ready = True
                retry_delay = _RETRY_INITIAL_DELAY
                if connection_listener is not None:
                    connection_listener(True)

            try:
                await self._run_websocket_once(devices, listener, ready)
            except AuxRateLimitError as exc:
                retry_after = exc.retry_after
                _LOGGER.debug("AUX websocket runner was rate limited")
            except AuxApiError as exc:
                _LOGGER.debug(
                    "AUX websocket runner restarting (%s)", type(exc).__name__
                )
            except Exception:
                _LOGGER.exception("Unexpected AUX websocket runner failure")

            if connection_listener is not None:
                connection_listener(False)
            retry_floor = max(retry_delay, retry_after or 0)
            await asyncio.sleep(retry_floor * random.uniform(1, 1.2))  # noqa: S311
            if not reached_ready:
                retry_delay = min(retry_delay * 2, _RETRY_MAX_DELAY)

    async def update_realtime_devices(self, devices: list[AuxDevice]) -> None:
        """Reset subscriptions on the active relay connection."""
        if self._websocket is not None and self._websocket.connected:
            await self._websocket.subscribe_devices(devices)

    async def close(self) -> None:
        """Close the websocket connection."""
        if self._websocket is not None:
            await self._websocket.async_close()
            self._websocket = None


def _deduplicate_devices(devices: list[AuxDevice]) -> list[AuxDevice]:
    deduplicated: list[AuxDevice] = []
    seen: set[str] = set()
    for device in devices:
        endpoint_id = device.get("endpointId")
        if endpoint_id and endpoint_id in seen:
            continue
        if endpoint_id:
            seen.add(endpoint_id)
        deduplicated.append(device)
    return deduplicated


def _preferred_query_error(errors: list[BaseException]) -> BaseException:
    for error_type in (
        AuxAuthError,
        AuxSessionExpired,
        AuxRateLimitError,
        AuxServerError,
        AuxNetworkError,
        AuxApiError,
    ):
        for error in errors:
            if isinstance(error, error_type):
                return error
    return errors[0]
