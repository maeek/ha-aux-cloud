"""AUX Cloud API facade."""

from __future__ import annotations

from typing import TypedDict

import aiohttp

from ..devices.normalizers import (
    normalize_device_params,
)
from .control import AuxCloudControlService, AuxCloudWebSocketStrategy
from .errors import AuxApiError, AuxNetworkError, AuxServerError, AuxSessionExpired
from .protocol.common import (
    build_device_params_directive,
    build_directive_header,
    decode_json_payload,
    parse_std_data,
)
from .protocol.websocket import extract_websocket_updates
from .repository import AuxCloudRepository
from .session import (
    COMPANY_ID,
    LICENSE,
    LICENSE_ID,
    AuxCloudSession,
)
from .transports.http import AuxCloudHttpStrategy, parse_control_event
from .transports.websocket import (
    AuxCloudWebSocket,
    websocket_origin,
)


class DirectiveStuData(TypedDict):
    did: str
    devtype: int
    devSession: str


class ExpiredTokenError(AuxSessionExpired):
    """Raised when an AUX Cloud token expires."""


class AuxCloudAPI:  # pylint: disable=too-many-public-methods
    """Stable facade for interacting with AUX Cloud services."""

    def __init__(
        self, region: str = "eu", session: aiohttp.ClientSession | None = None
    ) -> None:
        """Initialize the AUX Cloud facade."""
        self.session = AuxCloudSession(region=region, session=session)
        self.ws_api: AuxCloudWebSocket | None = None
        self._http_strategy = AuxCloudHttpStrategy(
            self._make_request, self._get_headers, LICENSE
        )
        self._websocket_strategy = AuxCloudWebSocketStrategy(
            lambda: self.ws_api, self._get_app_header
        )
        self.control = AuxCloudControlService(
            self._http_strategy, self._websocket_strategy
        )
        self.repository = AuxCloudRepository(self.session, self.control)

    @property
    def url(self) -> str:
        """Return the selected regional API base URL."""
        return self.session.url

    @property
    def region(self) -> str:
        """Return the configured region."""
        return self.session.region

    @property
    def email(self) -> str | None:
        """Return the configured account email."""
        return self.session.email

    @email.setter
    def email(self, value: str | None) -> None:
        self.session.email = value

    @property
    def phone_number(self) -> str | None:
        """Return the configured account phone number."""
        return self.session.phone_number

    @phone_number.setter
    def phone_number(self, value: str | None) -> None:
        self.session.phone_number = value

    @property
    def password(self) -> str | None:
        """Return the configured account password."""
        return self.session.password

    @password.setter
    def password(self, value: str | None) -> None:
        self.session.password = value

    @property
    def loginsession(self) -> str | None:
        """Return the cloud login session ID."""
        return self.session.loginsession

    @loginsession.setter
    def loginsession(self, value: str | None) -> None:
        self.session.loginsession = value

    @property
    def userid(self) -> str | None:
        """Return the cloud user ID."""
        return self.session.userid

    @userid.setter
    def userid(self, value: str | None) -> None:
        self.session.userid = value

    @property
    def families(self) -> dict | None:
        """Return cached family data."""
        return self.repository.families

    @families.setter
    def families(self, value: dict | None) -> None:
        self.repository.families = value

    @property
    def http_strategy(self) -> AuxCloudHttpStrategy:
        """Return the HTTP control strategy."""
        return self._http_strategy

    @http_strategy.setter
    def http_strategy(self, strategy: AuxCloudHttpStrategy) -> None:
        self._http_strategy = strategy
        self.control.http_strategy = strategy

    @property
    def websocket_strategy(self) -> AuxCloudWebSocketStrategy:
        """Return the websocket control strategy."""
        return self._websocket_strategy

    @websocket_strategy.setter
    def websocket_strategy(self, strategy: AuxCloudWebSocketStrategy) -> None:
        self._websocket_strategy = strategy
        self.control.websocket_strategy = strategy

    def _get_headers(self, **kwargs: str) -> dict:
        """Compatibility wrapper for AUX Cloud app headers."""
        return self.session.get_headers(**kwargs)

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        headers: dict | None = None,
        data: dict | None = None,
        data_raw: str | bytes | None = None,
        params: dict | None = None,
    ) -> dict:
        """Compatibility wrapper for HTTP requests."""
        return await self.session.make_request(
            method=method,
            endpoint=endpoint,
            headers=headers,
            data=data,
            data_raw=data_raw,
            params=params,
        )

    async def login(
        self,
        email: str | None = None,
        password: str | None = None,
        *,
        phone_number: str | None = None,
    ) -> bool:
        """Login to AUX Cloud services."""
        try:
            return await self.session.login(
                email,
                password,
                phone_number=phone_number,
            )
        except ValueError as exc:
            raise AuxApiError(str(exc)) from exc

    def is_logged_in(self) -> bool:
        """Check if the user is logged in."""
        return self.session.is_logged_in()

    async def get_families(self):
        """List families associated with the user."""
        try:
            return await self.repository.get_families()
        except ValueError as exc:
            raise AuxApiError(str(exc)) from exc

    async def get_rooms(self, familyid: str):
        """List rooms associated with a family."""
        try:
            return await self.repository.get_rooms(familyid)
        except ValueError as exc:
            raise AuxApiError(str(exc)) from exc

    async def get_devices(
        self,
        familyid: str,
        shared=False,
    ):
        """List devices associated with a family."""
        try:
            return await self.repository.get_devices(familyid, shared)
        except ValueError as exc:
            raise AuxApiError(str(exc)) from exc

    def normalize_device_params(self, device: dict) -> None:
        """Normalize decoded params in-place."""
        normalize_device_params(device)

    def _get_directive_header(
        self, namespace: str, name: str, message_id_prefix: str, **kwargs: str
    ):
        """Compatibility wrapper for directive headers."""
        return build_directive_header(namespace, name, message_id_prefix, **kwargs)

    async def query_device_state(self, device_id: str, dev_session: str):
        """Query one device state."""
        try:
            return await self.repository.query_device_state(device_id, dev_session)
        except ValueError as exc:
            raise AuxApiError(str(exc)) from exc

    async def bulk_query_device_state(self, devices: list[dict]):
        """Query state for a list of devices."""
        try:
            return await self.repository.bulk_query_device_state(devices)
        except ValueError as exc:
            raise AuxApiError(str(exc)) from exc

    def _get_app_header(self, family_id: str | None = None) -> dict:
        """Return the app relay header used inside transit.opencontrol."""
        return {
            "familyId": family_id or "",
            "language": "en",
            "licenseid": LICENSE_ID,
            "loginsession": self.loginsession or "",
            "userid": self.userid or "",
        }

    def _build_device_params_directive(
        self,
        device: dict,
        act: str,
        params: list[str] | None = None,
        vals: list | None = None,
    ) -> dict:
        """Build a KeyValueControl directive for compatibility callers."""
        return build_device_params_directive(device, act, params, vals)

    async def _act_device_params_http(
        self,
        device: dict,
        act: str,
        params: list[str] | None = None,
        vals: list | None = None,
    ):
        """Query or set device parameters over HTTP."""
        try:
            return await self.http_strategy.act_device_params(device, act, params, vals)
        except ValueError as exc:
            raise AuxApiError(str(exc)) from exc

    async def _act_device_params_websocket(
        self,
        device: dict,
        act: str,
        params: list[str] | None = None,
        vals: list | None = None,
    ):
        """Query or set device parameters over websocket."""
        try:
            return await self.websocket_strategy.act_device_params(
                device, act, params, vals
            )
        except ValueError as exc:
            raise AuxApiError(str(exc)) from exc

    @staticmethod
    def _parse_std_data(data: str | dict | None) -> dict:
        """Parse Broadlink std data into a param dictionary."""
        return parse_std_data(data)

    @classmethod
    def _parse_control_event(cls, event: dict) -> dict:
        """Parse a KeyValueControl event response."""
        return parse_control_event(event)

    @staticmethod
    def _decode_json_payload(value) -> dict:
        """Decode a websocket payload value into a dict."""
        return decode_json_payload(value)

    async def get_device_params(self, device: dict, params: list[str] | None = None):
        """Query device parameters over HTTP."""
        try:
            return await self.control.get_device_params(device, params)
        except ValueError as exc:
            raise AuxApiError(str(exc)) from exc

    async def set_device_params(self, device: dict, values: dict):
        """Set device parameters, preferring websocket and falling back to HTTP."""
        try:
            return await self.control.set_device_params(device, values)
        except ValueError as exc:
            raise AuxApiError(str(exc)) from exc

    async def get_websocket_urls(self) -> list[str]:
        """Get websocket relay URLs from the cloud."""
        try:
            json_data = await self._make_request(
                method="POST",
                endpoint="appsync/apprelay/geturl",
                headers=self._get_headers(),
            )
            urls = json_data.get("data", {}).get("url", [])
            if json_data.get("status") == 0 and urls:
                return urls
        except (AuxNetworkError, AuxServerError):
            pass

        return []

    def _build_websocket_client(self, websocket_url: str, devices: list[dict] | None):
        """Build a websocket transport for the selected relay URL."""
        if self.loginsession is None or self.userid is None:
            raise AuxSessionExpired("AUX Cloud websocket authentication is missing")
        origin = websocket_origin(websocket_url) or self.url
        return AuxCloudWebSocket(
            websocket_url=websocket_url,
            headers=self._get_headers(
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

    async def initialize_websocket(
        self,
        devices: list[dict] | None = None,
        listener=None,
    ):
        """Deprecated: run websocket updates with async_run_websocket instead."""
        await self.async_run_websocket(devices=devices, listener=listener)

    async def _refresh_websocket_auth(self, websocket_url: str) -> dict:
        """Refresh login credentials for websocket reconnect."""
        if not self.password or not (self.email or self.phone_number):
            raise AuxApiError("Cannot refresh websocket auth without credentials.")

        await self.session.recover_session(expired_session=self.loginsession)
        origin = websocket_origin(websocket_url) or self.url
        return {
            "loginsession": self.loginsession,
            "userid": self.userid,
            "headers": self._get_headers(
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
