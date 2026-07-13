"""AUX Cloud API facade."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import aiohttp

from .control import AuxCloudControl
from .errors import AuxApiError, AuxSessionExpired
from .models import AuxCredentials, AuxDevice, DeviceUpdate
from .repository import AuxCloudRepository
from .session import (
    COMPANY_ID,
    LICENSE_ID,
    AuxCloudSession,
)
from .transports.websocket import (
    AuxCloudWebSocket,
    websocket_origin,
)


class AuxCloudAPI:
    """Stable facade for interacting with AUX Cloud services."""

    def __init__(self, region: str, session: aiohttp.ClientSession) -> None:
        """Initialize the AUX Cloud facade."""
        self._session = AuxCloudSession(region=region, session=session)
        self._websocket: AuxCloudWebSocket | None = None
        self._control = AuxCloudControl(
            self._session,
            lambda: self._websocket,
            self._get_app_header,
        )
        self._repository = AuxCloudRepository(self._session, self._control)

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
        return await self._repository.get_families()

    async def get_devices(
        self,
        familyid: str,
        shared: bool = False,
    ) -> list[AuxDevice]:
        """List devices associated with a family."""
        return await self._repository.get_devices(familyid, shared)

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
            return await self._control.set_device_params(device, values)
        except AuxSessionExpired:
            await self.close_websocket()
            await self._session.recover_session(expired_session=expired_session)
            return await self._control.set_device_params_http(device, values)

    async def get_websocket_urls(self) -> list[str]:
        """Get websocket relay URLs from the cloud."""
        json_data = await self._session.make_request(
            endpoint="appsync/apprelay/geturl",
        )
        urls = json_data.get("data", {}).get("url", [])
        return urls if json_data.get("status") == 0 and urls else []

    def _build_websocket_client(
        self, websocket_url: str, devices: list[AuxDevice] | None
    ) -> AuxCloudWebSocket:
        """Build a websocket transport for the selected relay URL."""
        if self._session.loginsession is None or self._session.userid is None:
            raise AuxSessionExpired("AUX Cloud websocket authentication is missing")
        origin = websocket_origin(websocket_url) or self._session.url
        return AuxCloudWebSocket(
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

    async def async_run_websocket(
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

    async def async_update_websocket_subscriptions(
        self, devices: list[AuxDevice]
    ) -> None:
        """Reset subscriptions on the active relay connection."""
        if self._websocket is not None and self._websocket.connected:
            await self._websocket.subscribe_devices(devices)

    async def close_websocket(self) -> None:
        """Close the websocket connection."""
        if self._websocket is not None:
            await self._websocket.async_close()
            self._websocket = None
