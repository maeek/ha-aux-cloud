"""WebSocket transport for AUX Cloud."""

# pylint: disable=too-many-instance-attributes

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from urllib.parse import urlparse

import aiohttp

from ..errors import AuxApiError, raise_for_cloud_response

_LOGGER = logging.getLogger(__name__)

WEBSOCKET_SERVER_URL_EU = "wss://app-relay-deu-f0e9ebbb.smarthomecs.de"
WEBSOCKET_SERVER_URL_USA = "wss://app-relay-usa-fd7cc04c.smarthomecs.com"
WEBSOCKET_SERVER_URL_CN = "wss://app-relay-chn-31a93883.ibroadlink.com"
RELAY_CONNECT_PATH = "/appsync/apprelay/relayconnect"

PING_INTERVAL = 20
CONNECT_TIMEOUT = 10
COMMAND_TIMEOUT = 10
RECONNECT_INITIAL_DELAY = 5
RECONNECT_MAX_DELAY = 60

MessageListener = Callable[[dict], Awaitable[None] | None]
AuthRefreshCallback = Callable[[str], Awaitable[dict]]


class AuxWebSocketState(Enum):
    """Connection state for the AUX Cloud websocket runner."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPED = "stopped"


ConnectionStateListener = Callable[[AuxWebSocketState], Awaitable[None] | None]


def websocket_origin(websocket_url: str) -> str:
    """Return the Origin header value used by the Android app."""
    host = urlparse(websocket_url).hostname
    return f"https://{host}" if host else ""


def websocket_connect_url(websocket_url: str) -> str:
    """Return the full relay connect URL without duplicating the relay path."""
    normalized_url = websocket_url.rstrip("/")
    if urlparse(normalized_url).path.rstrip("/") == RELAY_CONNECT_PATH:
        return normalized_url
    return f"{normalized_url}{RELAY_CONNECT_PATH}"


class AuxCloudWebSocket:
    """Single-runner AUX Cloud websocket transport."""

    def __init__(
        self,
        *,
        websocket_url: str,
        headers: dict,
        loginsession: str,
        userid: str,
        session: aiohttp.ClientSession | None = None,
        auth_refresh_callback: AuthRefreshCallback | None = None,
        devices: list[dict] | None = None,
    ) -> None:
        """Initialize the websocket transport."""
        self.websocket_url = websocket_url
        self.headers = headers
        self.loginsession = loginsession
        self.userid = userid
        self._auth_refresh_callback = auth_refresh_callback

        self._session = session
        self._owns_session = session is None
        self.websocket: aiohttp.ClientWebSocketResponse | None = None

        self._subscriptions: list[dict] = []
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._send_lock = asyncio.Lock()
        self._ready = asyncio.Event()
        self._closed = False
        self._auth_failed = False
        self._message_counter = 0
        self._state = AuxWebSocketState.DISCONNECTED

        if devices:
            self.set_subscriptions(devices)

    @property
    def api_initialized(self) -> bool:
        """Return whether the relay init handshake succeeded."""
        return self._ready.is_set()

    @property
    def connected(self) -> bool:
        """Return whether the websocket is connected and ready for commands."""
        return (
            self.websocket is not None
            and not self.websocket.closed
            and self._ready.is_set()
        )

    async def async_run(
        self,
        on_message: MessageListener | None = None,
        on_connection_state: ConnectionStateListener | None = None,
    ) -> None:
        """Run the websocket until cancelled or closed."""
        self._closed = False
        reconnect_delay = RECONNECT_INITIAL_DELAY

        try:
            while not self._closed:
                try:
                    await self._emit_state(
                        AuxWebSocketState.CONNECTING, on_connection_state
                    )
                    if self._auth_failed:
                        await self._refresh_auth()
                    await self._connect_and_subscribe(on_message)
                    reconnect_delay = RECONNECT_INITIAL_DELAY
                    await self._emit_state(AuxWebSocketState.READY, on_connection_state)
                    await self._read_loop(on_message)
                    raise ConnectionError("AUX Cloud websocket closed")
                except Exception as exc:  # pylint: disable=broad-except
                    if self._closed:
                        break
                    _LOGGER.debug(
                        "AUX Cloud websocket reconnecting (%s)", type(exc).__name__
                    )
                    await self._close_socket()
                    await self._emit_state(
                        AuxWebSocketState.DEGRADED, on_connection_state
                    )
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX_DELAY)
        finally:
            self._closed = True
            await self._close_socket()
            self._cancel_pending()
            await self._emit_state(AuxWebSocketState.STOPPED, on_connection_state)
            if self._owns_session and self._session is not None:
                await self._session.close()
            self._session = None

    async def async_close(self) -> None:
        """Close the websocket and cancel pending responses."""
        self._closed = True
        await self._close_socket()
        self._cancel_pending()
        if self._owns_session and self._session is not None:
            await self._session.close()
        self._session = None

    async def close_websocket(self) -> None:
        """Backward-compatible close alias."""
        await self.async_close()

    def set_subscriptions(self, devices: list[dict]) -> None:
        """Store the device subscription list for initial connect and reconnect."""
        self._subscriptions = [
            {
                "devSession": device.get("devSession", ""),
                "endpointId": device["endpointId"],
                "gatewayId": device.get("gatewayId", ""),
                "pid": device.get("productId", ""),
            }
            for device in devices
            if device.get("endpointId")
        ]

    async def subscribe_devices(
        self, devices: list[dict], *, reset: bool = True
    ) -> dict:
        """Subscribe to device status pushes on the active socket."""
        self.set_subscriptions(devices)
        return await self._subscribe_from_cache(reset=reset)

    async def async_send_opencontrol(
        self, data: dict, *, timeout: int = COMMAND_TIMEOUT
    ) -> dict:
        """Send a transit.opencontrol message and wait for its response."""
        if not self.connected:
            raise ConnectionError("WebSocket is not connected")
        return await self.send_data(
            {
                "data": data,
                "msgtype": "transit.opencontrol",
            },
            wait_response=True,
            timeout=timeout,
        )

    async def send_opencontrol(
        self, data: dict, *, timeout: int = COMMAND_TIMEOUT
    ) -> dict:
        """Backward-compatible opencontrol alias."""
        return await self.async_send_opencontrol(data, timeout=timeout)

    async def send_data(
        self,
        data: dict,
        *,
        reliable: bool = False,  # pylint: disable=unused-argument
        wait_response: bool = False,
        timeout: int | None = None,
    ) -> dict:
        """Send a JSON message to the websocket."""
        if not self.websocket or self.websocket.closed:
            raise ConnectionError("WebSocket is not connected")

        payload = dict(data)
        message_id = str(payload.get("messageid") or self._next_message_id())
        payload["messageid"] = message_id

        future: asyncio.Future[dict] | None = None
        if wait_response:
            future = asyncio.get_running_loop().create_future()
            self._pending[message_id] = future

        try:
            await self._send_raw(json.dumps(payload, separators=(",", ":")))
            if future is None:
                return {}
            return await asyncio.wait_for(future, timeout=timeout)
        except Exception:
            self._pending.pop(message_id, None)
            raise

    async def _connect_and_subscribe(self, on_message: MessageListener | None) -> None:
        """Open the socket, authenticate, and subscribe to device pushes."""
        self._ready.clear()
        await self._open_socket()

        init_response = await self._send_and_wait(
            {
                "data": {"relayrule": "share"},
                "msgtype": "init",
                "scope": {
                    "loginsession": self.loginsession,
                    "userid": self.userid,
                },
            },
            expected_msgtype="initk",
            timeout=CONNECT_TIMEOUT,
            on_message=on_message,
        )
        try:
            raise_for_cloud_response(init_response, endpoint="websocket/init")
        except AuxApiError as exc:
            self._auth_failed = True
            raise ConnectionError("AUX Cloud websocket init failed") from exc
        if not self._is_success_status(init_response.get("status")):
            self._auth_failed = True
            raise ConnectionError("AUX Cloud websocket init failed")

        self._auth_failed = False
        if self._subscriptions:
            await self._subscribe_from_cache(on_message=on_message, reset=True)
        self._ready.set()

    async def _open_socket(self) -> None:
        """Open the websocket connection."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True

        url = websocket_connect_url(self.websocket_url)
        self.websocket = await self._session.ws_connect(
            url,
            headers=self.headers,
            timeout=CONNECT_TIMEOUT,
        )
        _LOGGER.debug("AUX Cloud websocket connection established")

    async def _read_loop(self, on_message: MessageListener | None) -> None:
        """Read pushed messages and send app-level pings when idle."""
        while not self._closed and self.websocket and not self.websocket.closed:
            try:
                msg = await asyncio.wait_for(
                    self.websocket.receive(), timeout=PING_INTERVAL
                )
            except TimeoutError:
                await self._ping(on_message)
                continue
            await self._handle_ws_message(msg, on_message)

    async def _ping(self, on_message: MessageListener | None) -> None:
        """Send app-level ping and require a successful ping ACK."""
        response = await self._send_and_wait(
            {"msgtype": "ping"},
            expected_msgtype="pingk",
            timeout=COMMAND_TIMEOUT,
            on_message=on_message,
        )
        try:
            raise_for_cloud_response(response, endpoint="websocket/ping")
        except AuxApiError as exc:
            self._auth_failed = True
            raise ConnectionError("AUX Cloud websocket ping failed") from exc
        if not self._is_success_status(response.get("status")):
            self._auth_failed = True
            raise ConnectionError("AUX Cloud websocket ping failed")

    async def _subscribe_from_cache(
        self,
        *,
        on_message: MessageListener | None = None,
        reset: bool = True,
    ) -> dict:
        """Subscribe the cached device list on the active socket."""
        if not self._subscriptions:
            return {}

        response = await self._send_and_wait(
            {
                "data": {"devList": self._subscriptions},
                "msgtype": "subreset" if reset else "sub",
                "topic": "devpush",
            },
            expected_msgtype="subresetk" if reset else "subk",
            timeout=COMMAND_TIMEOUT,
            on_message=on_message,
        )
        self._validate_subscription_response(response)
        return response

    async def _send_and_wait(
        self,
        data: dict,
        *,
        expected_msgtype: str,
        timeout: int,
        on_message: MessageListener | None,
    ) -> dict:
        """Send a request and read messages until its ACK arrives."""
        if self.websocket is None or self.websocket.closed:
            raise ConnectionError("WebSocket is not connected")

        payload = dict(data)
        message_id = str(payload.get("messageid") or self._next_message_id())
        payload["messageid"] = message_id
        await self._send_raw(json.dumps(payload, separators=(",", ":")))

        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for {expected_msgtype}")

            msg = await asyncio.wait_for(self.websocket.receive(), timeout=remaining)
            response = await self._handle_ws_message(msg, on_message)
            if str(response.get("messageid", "")) != message_id:
                continue
            if response.get("msgtype") != expected_msgtype:
                raise ConnectionError(
                    f"Unexpected websocket response for {message_id}: {response}"
                )
            return response

    async def _handle_ws_message(
        self,
        msg: aiohttp.WSMessage,
        on_message: MessageListener | None,
    ) -> dict:
        """Handle a websocket message object."""
        if msg.type == aiohttp.WSMsgType.TEXT:
            return await self._handle_text_message(msg.data, on_message)

        if msg.type in (
            aiohttp.WSMsgType.CLOSE,
            aiohttp.WSMsgType.CLOSED,
            aiohttp.WSMsgType.ERROR,
        ):
            raise ConnectionError(f"AUX Cloud websocket closed: {msg.type}")

        return {}

    async def _handle_text_message(
        self,
        raw_data: str,
        on_message: MessageListener | None = None,
    ) -> dict:
        """Handle a text websocket message."""
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            _LOGGER.debug("Ignoring non-JSON AUX websocket message")
            return {}

        message_id = str(data.get("messageid", ""))
        msgtype = data.get("msgtype")
        if message_id:
            future = self._pending.pop(message_id, None)
            if future is not None and not future.done():
                future.set_result(data)

        if msgtype in {"initk", "pingk"}:
            return data

        _LOGGER.debug("AUX Cloud websocket message received (%s)", msgtype)
        if on_message is not None:
            await self._notify_listener(on_message, data)
        return data

    async def _notify_listener(self, listener: MessageListener, message: dict) -> None:
        """Notify the registered listener with a websocket message."""
        try:
            result = listener(message)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.error(
                "Error in AUX Cloud websocket listener (%s)", type(exc).__name__
            )

    async def _send_raw(self, raw_data: str) -> None:
        """Send a raw websocket string."""
        if not self.websocket or self.websocket.closed:
            raise ConnectionError("WebSocket is not connected")

        async with self._send_lock:
            await self.websocket.send_str(raw_data)
            _LOGGER.debug("AUX Cloud websocket message sent")

    async def _refresh_auth(self) -> None:
        """Refresh login/session data before reconnecting."""
        if self._auth_refresh_callback is None:
            return

        auth_data = await self._auth_refresh_callback(self.websocket_url)
        self.loginsession = auth_data.get("loginsession", self.loginsession)
        self.userid = auth_data.get("userid", self.userid)
        self.headers = auth_data.get("headers", self.headers)
        self._auth_failed = False

    async def _emit_state(
        self,
        state: AuxWebSocketState,
        listener: ConnectionStateListener | None,
    ) -> None:
        """Emit connection state changes."""
        if self._state == state:
            return
        self._state = state
        if listener is None:
            return
        result = listener(state)
        if inspect.isawaitable(result):
            await result

    async def _close_socket(self) -> None:
        """Close the active websocket."""
        self._ready.clear()
        if self.websocket is not None and not self.websocket.closed:
            with contextlib.suppress(Exception):
                await self.websocket.close()
        self.websocket = None

    def _cancel_pending(self) -> None:
        """Cancel pending command futures."""
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

    @classmethod
    def _validate_subscription_response(cls, response: dict) -> None:
        """Raise if the relay rejected a subscription request."""
        try:
            raise_for_cloud_response(response, endpoint="websocket/subscribe")
        except AuxApiError as exc:
            raise ConnectionError("AUX Cloud websocket subscription failed") from exc

        if not cls._is_success_status(response.get("status")):
            raise ConnectionError("AUX Cloud websocket subscription failed")

        failed_devices = []
        for item in (response.get("data") or {}).get("devList", []) or []:
            try:
                raise_for_cloud_response(item, endpoint="websocket/subscribe")
            except AuxApiError as exc:
                raise ConnectionError(
                    "AUX Cloud websocket subscription failed"
                ) from exc
            if not cls._is_success_status(item.get("status")):
                failed_devices.append(item.get("endpointId") or item.get("did"))

        if failed_devices:
            raise ConnectionError(
                "AUX Cloud websocket subscription failed for a device"
            )

    def _next_message_id(self) -> str:
        """Return a mostly monotonic millisecond message id."""
        self._message_counter = (self._message_counter + 1) % 1000
        return f"{int(time.time() * 1000)}{self._message_counter:03d}"

    @staticmethod
    def _is_success_status(status) -> bool:
        """Return whether a relay status value represents success."""
        return status in (None, 0, "0")
