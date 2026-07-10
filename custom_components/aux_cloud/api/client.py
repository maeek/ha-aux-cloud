"""AUX Cloud API facade."""

from __future__ import annotations

import aiohttp

from ..devices.normalizers import (
    normalize_device_params,
)
from .control import AuxCloudControlService, AuxCloudWebSocketStrategy
from .errors import AuxApiError, AuxSessionExpired
from .protocol.websocket import extract_websocket_updates
from .repository import AuxCloudRepository
from .session import (
    COMPANY_ID,
    LICENSE,
    LICENSE_ID,
    AuxCloudSession,
)
from .transports.http import AuxCloudHttpStrategy
from .transports.websocket import (
    AuxCloudWebSocket,
    websocket_origin,
)


class AuxCloudAPI:
    """Stable facade for interacting with AUX Cloud services."""

    def __init__(
        self, region: str = "eu", session: aiohttp.ClientSession | None = None
    ) -> None:
        """Initialize the AUX Cloud facade."""
        self.session = AuxCloudSession(region=region, session=session)
        self.ws_api: AuxCloudWebSocket | None = None
        http_strategy = AuxCloudHttpStrategy(
            self.session.make_request, self.session.get_headers, LICENSE
        )
        websocket_strategy = AuxCloudWebSocketStrategy(
            lambda: self.ws_api, self._get_app_header
        )
        self.control = AuxCloudControlService(http_strategy, websocket_strategy)
        self.repository = AuxCloudRepository(self.session, self.control)

    @property
    def loginsession(self) -> str | None:
        """Return the cloud login session ID."""
        return self.session.loginsession

    @property
    def userid(self) -> str | None:
        """Return the cloud user ID."""
        return self.session.userid

    @property
    def families(self) -> dict | None:
        """Return cached family data."""
        return self.repository.families

    @property
    def http_strategy(self) -> AuxCloudHttpStrategy:
        """Return the HTTP control strategy."""
        return self.control.http_strategy

    @property
    def websocket_strategy(self) -> AuxCloudWebSocketStrategy:
        """Return the websocket control strategy."""
        return self.control.websocket_strategy

    async def login(
        self,
        email: str | None = None,
        password: str | None = None,
        *,
        phone_number: str | None = None,
    ) -> bool:
        """Login to AUX Cloud services."""
        return await self.session.login(
            email,
            password,
            phone_number=phone_number,
        )

    def is_logged_in(self) -> bool:
        """Check if the user is logged in."""
        return self.session.is_logged_in()

    async def get_families(self):
        """List families associated with the user."""
        return await self.repository.get_families()

    async def get_rooms(self, familyid: str):
        """List rooms associated with a family."""
        return await self.repository.get_rooms(familyid)

    async def get_devices(
        self,
        familyid: str,
        shared=False,
    ):
        """List devices associated with a family."""
        return await self.repository.get_devices(familyid, shared)

    def normalize_device_params(self, device: dict) -> None:
        """Normalize decoded params in-place."""
        normalize_device_params(device)

    async def query_device_state(self, device_id: str, dev_session: str):
        """Query one device state."""
        return await self.repository.query_device_state(device_id, dev_session)

    async def bulk_query_device_state(self, devices: list[dict]):
        """Query state for a list of devices."""
        return await self.repository.bulk_query_device_state(devices)

    def _get_app_header(self, family_id: str | None = None) -> dict:
        """Return the app relay header used inside transit.opencontrol."""
        return {
            "familyId": family_id or "",
            "language": "en",
            "licenseid": LICENSE_ID,
            "loginsession": self.loginsession or "",
            "userid": self.userid or "",
        }

    async def get_device_params(self, device: dict, params: list[str] | None = None):
        """Query device parameters over HTTP."""
        return await self.control.get_device_params(device, params)

    async def set_device_params(self, device: dict, values: dict):
        """Set device parameters, preferring websocket and falling back to HTTP."""
        return await self.control.set_device_params(device, values)

    async def get_websocket_urls(self) -> list[str]:
        """Get websocket relay URLs from the cloud."""
        json_data = await self.session.make_request(
            method="POST",
            endpoint="appsync/apprelay/geturl",
            headers=self.session.get_headers(),
        )
        urls = json_data.get("data", {}).get("url", [])
        return urls if json_data.get("status") == 0 and urls else []

    def _build_websocket_client(self, websocket_url: str, devices: list[dict] | None):
        """Build a websocket transport for the selected relay URL."""
        if self.loginsession is None or self.userid is None:
            raise AuxSessionExpired("AUX Cloud websocket authentication is missing")
        origin = websocket_origin(websocket_url) or self.session.url
        return AuxCloudWebSocket(
            websocket_url=websocket_url,
            headers=self.session.get_headers(
                CompanyId=COMPANY_ID,
                Origin=origin,
                licenseid=LICENSE_ID,
            ),
            loginsession=self.loginsession,
            userid=self.userid,
            session=self.session._session,  # pylint: disable=protected-access
            auth_refresh_callback=self._refresh_websocket_auth,
            devices=devices,
        )

    async def async_run_websocket(
        self,
        devices: list[dict] | None = None,
        listener=None,
        state_listener=None,
    ):
        """Run the WebSocket connection to receive real-time updates."""
        if not self.is_logged_in():
            raise AuxApiError("Cannot run WebSocket without being logged in.")

        urls = await self.get_websocket_urls()
        if not urls:
            raise AuxApiError("No AUX Cloud websocket relay URL available.")

        websocket_url = urls[0].rstrip("/")
        self.ws_api = self._build_websocket_client(websocket_url, devices)
        try:
            await self.ws_api.async_run(listener, state_listener)
        finally:
            self.ws_api = None

    async def _refresh_websocket_auth(self, websocket_url: str) -> dict:
        """Refresh login credentials for websocket reconnect."""
        if not self.session.password or not (
            self.session.email or self.session.phone_number
        ):
            raise AuxApiError("Cannot refresh websocket auth without credentials.")

        await self.session.recover_session(expired_session=self.loginsession)
        origin = websocket_origin(websocket_url) or self.session.url
        return {
            "loginsession": self.loginsession,
            "userid": self.userid,
            "headers": self.session.get_headers(
                CompanyId=COMPANY_ID,
                Origin=origin,
                licenseid=LICENSE_ID,
            ),
        }

    async def close_websocket(self) -> None:
        """Close the websocket connection."""
        if self.ws_api is not None:
            await self.ws_api.async_close()
            self.ws_api = None

    def extract_websocket_updates(self, message: dict) -> list[dict]:
        """Extract endpoint param updates from websocket messages."""
        return extract_websocket_updates(message)
