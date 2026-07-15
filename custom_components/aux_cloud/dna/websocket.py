"""Single-connection websocket primitives for the BroadLink DNA cloud."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import aiohttp

from ..api.errors import AuxNetworkError, AuxServerError
from ..api.models import AuxDevice, DeviceUpdate
from .codec import (
    build_device_subscriptions,
    extract_websocket_updates,
    validate_websocket_response,
)

_LOGGER = logging.getLogger(__name__)

RELAY_CONNECT_PATH = "/appsync/apprelay/relayconnect"

PING_INTERVAL = 20
CONNECT_TIMEOUT = 10
COMMAND_TIMEOUT = 10

Message = dict[str, Any]
MessageListener = Callable[[tuple[DeviceUpdate, ...]], None]
ReadyListener = Callable[[], None]
PendingResponse = tuple[asyncio.Future[Message], str]


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


def _next_message_id(counter: int) -> tuple[int, str]:
    """Return the next counter and a mostly monotonic millisecond message ID."""
    next_counter = (counter + 1) % 1000
    return next_counter, f"{int(time.time() * 1000)}{next_counter:03d}"


class DnaWebSocket:
    """Single-runner AUX Cloud websocket transport."""

    def __init__(
        self,
        *,
        websocket_url: str,
        headers: dict[str, str],
        loginsession: str,
        userid: str,
        session: aiohttp.ClientSession,
        devices: list[AuxDevice] | None = None,
    ) -> None:
        """Initialize the websocket transport."""
        self.websocket_url = websocket_url
        self.headers = headers
        self.loginsession = loginsession
        self.userid = userid

        self._session = session
        self.websocket: aiohttp.ClientWebSocketResponse | None = None

        self._subscriptions: list[Message] = []
        self._pending: dict[str, PendingResponse] = {}
        self._send_lock = asyncio.Lock()
        self._ready = asyncio.Event()
        self._closed = False
        self._message_counter = 0
        self._last_message_at = 0.0
        self._listener: MessageListener | None = None

        if devices:
            self.set_subscriptions(devices)

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
        on_ready: ReadyListener | None = None,
    ) -> None:
        """Run one websocket connection until it closes or is cancelled."""
        self._closed = False
        self._listener = on_message
        reader_task: asyncio.Task[None] | None = None
        heartbeat_task: asyncio.Task[None] | None = None

        try:
            await self._open_socket()
            self._last_message_at = asyncio.get_running_loop().time()
            reader_task = asyncio.create_task(
                self._read_loop(),
                name="aux_cloud_websocket_reader",
            )
            await self._initialize()
            self._ready.set()
            if on_ready is not None:
                on_ready()
            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(),
                name="aux_cloud_websocket_heartbeat",
            )
            await asyncio.gather(reader_task, heartbeat_task)
        finally:
            self._closed = True
            self._listener = None
            for task in (reader_task, heartbeat_task):
                if task is not None and not task.done():
                    task.cancel()
            tasks = [task for task in (reader_task, heartbeat_task) if task is not None]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await self._close_socket()
            self._terminate_pending()

    async def async_close(self) -> None:
        """Close the websocket and cancel pending responses."""
        self._closed = True
        await self._close_socket()
        self._terminate_pending()

    def set_subscriptions(self, devices: list[AuxDevice]) -> None:
        """Store the device subscription list for initial connect and reconnect."""
        self._subscriptions = build_device_subscriptions(devices)

    async def subscribe_devices(self, devices: list[AuxDevice]) -> Message:
        """Subscribe to device status pushes on the active socket."""
        self.set_subscriptions(devices)
        return await self._subscribe_from_cache()

    async def async_send_opencontrol(
        self, data: Message, *, timeout: int = COMMAND_TIMEOUT
    ) -> Message:
        """Send a transit.opencontrol message and wait for its response."""
        if not self.connected:
            raise AuxNetworkError(
                "WebSocket is not connected",
                endpoint="websocket/transit.opencontrol",
            )
        return await self._request(
            {
                "data": data,
                "msgtype": "transit.opencontrol",
            },
            expected_msgtype="transit.opencontrolk",
            timeout=timeout,
            endpoint="websocket/transit.opencontrol",
        )

    async def _request(
        self,
        data: Message,
        *,
        expected_msgtype: str,
        timeout: int,
        endpoint: str,
    ) -> Message:
        """Send one request and await its correlated response from the reader."""
        if not self.websocket or self.websocket.closed:
            raise AuxNetworkError("WebSocket is not connected", endpoint=endpoint)

        payload = dict(data)
        message_id = str(payload.get("messageid", ""))
        if not message_id:
            self._message_counter, message_id = _next_message_id(self._message_counter)
        payload["messageid"] = message_id
        future: asyncio.Future[Message] = asyncio.get_running_loop().create_future()
        self._pending[message_id] = (future, expected_msgtype)

        try:
            try:
                async with asyncio.timeout(timeout):
                    await self._send_raw(json.dumps(payload, separators=(",", ":")))
                    return await future
            except TimeoutError as exc:
                raise AuxNetworkError(
                    f"Timed out waiting for {expected_msgtype}",
                    endpoint=endpoint,
                ) from exc
        finally:
            self._pending.pop(message_id, None)

    async def _initialize(self) -> None:
        """Authenticate the open socket and subscribe to device pushes."""
        self._ready.clear()

        init_response = await self._request(
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
            endpoint="websocket/init",
        )
        validate_websocket_response(init_response, endpoint="websocket/init")

        if self._subscriptions:
            await self._subscribe_from_cache()

    async def _open_socket(self) -> None:
        """Open the websocket connection."""
        url = websocket_connect_url(self.websocket_url)
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                self.websocket = await self._session.ws_connect(
                    url,
                    headers=self.headers,
                )
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise AuxNetworkError(endpoint="websocket/connect") from exc
        _LOGGER.debug("AUX Cloud websocket connection established")

    async def _read_loop(self) -> None:
        """Own all websocket receives and route messages to waiting requests."""
        try:
            while not self._closed and self.websocket and not self.websocket.closed:
                msg = await self.websocket.receive()
                self._last_message_at = asyncio.get_running_loop().time()
                await self._handle_ws_message(msg)
            if not self._closed:
                raise AuxNetworkError(
                    "AUX Cloud websocket closed",
                    endpoint="websocket/receive",
                )
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise AuxNetworkError(endpoint="websocket/receive") from exc
        finally:
            if not self._closed:
                self._terminate_pending(
                    AuxNetworkError(
                        "AUX Cloud websocket disconnected",
                        endpoint="websocket/receive",
                    )
                )

    async def _heartbeat_loop(self) -> None:
        """Send the vendor app-level ping after an idle interval."""
        while not self._closed:
            await asyncio.sleep(PING_INTERVAL)
            idle_for = asyncio.get_running_loop().time() - self._last_message_at
            if idle_for < PING_INTERVAL:
                continue
            await self._ping()

    async def _ping(self) -> None:
        """Send app-level ping and require a successful ping ACK."""
        response = await self._request(
            {"msgtype": "ping"},
            expected_msgtype="pingk",
            timeout=COMMAND_TIMEOUT,
            endpoint="websocket/ping",
        )
        validate_websocket_response(response, endpoint="websocket/ping")

    async def _subscribe_from_cache(self) -> Message:
        """Subscribe the cached device list on the active socket."""
        response = await self._request(
            {
                "data": {"devList": self._subscriptions},
                "msgtype": "subreset",
                "topic": "devpush",
            },
            expected_msgtype="subresetk",
            timeout=COMMAND_TIMEOUT,
            endpoint="websocket/subscribe",
        )
        validate_websocket_response(response, endpoint="websocket/subscribe")
        self._notify_updates(extract_websocket_updates(response))
        return response

    async def _handle_ws_message(
        self,
        msg: aiohttp.WSMessage,
    ) -> Message:
        """Handle a websocket message object."""
        if msg.type == aiohttp.WSMsgType.TEXT:
            return await self._handle_text_message(msg.data)

        if msg.type in (
            aiohttp.WSMsgType.CLOSE,
            aiohttp.WSMsgType.CLOSED,
            aiohttp.WSMsgType.ERROR,
        ):
            raise AuxNetworkError(
                f"AUX Cloud websocket closed: {msg.type}",
                endpoint="websocket/receive",
            )

        return {}

    async def _handle_text_message(
        self,
        raw_data: str,
    ) -> Message:
        """Handle a text websocket message."""
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            _LOGGER.debug("Ignoring non-JSON AUX websocket message")
            return {}
        if not isinstance(data, dict):
            _LOGGER.debug("Ignoring non-object AUX websocket message")
            return {}

        message_id = str(data.get("messageid", ""))
        msgtype = data.get("msgtype")
        if message_id:
            pending = self._pending.get(message_id)
            if pending is not None:
                future, expected_msgtype = pending
                if not future.done():
                    if msgtype == expected_msgtype:
                        future.set_result(data)
                        return data
                    future.set_exception(
                        AuxServerError(
                            f"Unexpected websocket response type {msgtype}",
                            endpoint="websocket/response",
                        )
                    )

        if msgtype in {"initk", "pingk", "transit.opencontrolk"}:
            return data

        _LOGGER.debug("AUX Cloud websocket message received (%s)", msgtype)
        if msgtype in {"subk", "subresetk"}:
            validate_websocket_response(data, endpoint="websocket/subscribe")
        self._notify_updates(extract_websocket_updates(data))
        return data

    def _notify_updates(
        self,
        updates: tuple[DeviceUpdate, ...],
    ) -> None:
        """Notify the owner without blocking the sole socket reader."""
        if not updates or self._listener is None:
            return
        try:
            self._listener(updates)
        except Exception:
            _LOGGER.exception("Error in AUX Cloud websocket listener")

    async def _send_raw(self, raw_data: str) -> None:
        """Send a raw websocket string."""
        if not self.websocket or self.websocket.closed:
            raise AuxNetworkError(
                "WebSocket is not connected",
                endpoint="websocket/send",
            )

        async with self._send_lock:
            try:
                await self.websocket.send_str(raw_data)
            except (aiohttp.ClientError, TimeoutError) as exc:
                raise AuxNetworkError(endpoint="websocket/send") from exc
            _LOGGER.debug("AUX Cloud websocket message sent")

    async def _close_socket(self) -> None:
        """Close the active websocket."""
        self._ready.clear()
        if self.websocket is not None and not self.websocket.closed:
            with contextlib.suppress(Exception):
                await self.websocket.close()
        self.websocket = None

    def _terminate_pending(self, error: AuxNetworkError | None = None) -> None:
        """Cancel or fail all pending requests during shutdown."""
        for future, _expected_msgtype in self._pending.values():
            if future.done():
                continue
            if error is None:
                future.cancel()
            else:
                future.set_exception(error)
        self._pending.clear()
