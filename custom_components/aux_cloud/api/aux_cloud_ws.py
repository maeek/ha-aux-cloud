import asyncio
import json
import logging
import time

import aiohttp

_LOGGER = logging.getLogger(__name__)

WEBSOCKET_SERVER_URL_EU = "wss://app-relay-deu-f0e9ebbb.smarthomecs.de"
WEBSOCKET_SERVER_URL_USA = "wss://app-relay-usa-fd7cc04c.smarthomecs.com"
WEBSOCKET_SERVER_URL_CN = "wss://app-relay-chn-31a93883.ibroadlink.com"


class AuxCloudWebSocket:
    def __init__(self, region: str, headers, loginsession, userid):
        self.websocket_url = (
            WEBSOCKET_SERVER_URL_EU
            if region == "eu"
            else (
                WEBSOCKET_SERVER_URL_USA if region == "usa" else WEBSOCKET_SERVER_URL_CN
            )
        )
        self.headers = headers
        self.loginsession = loginsession
        self.userid = userid

        self.websocket: aiohttp.ClientWebSocketResponse = None
        self._listeners = []
        self._reconnect_task = None
        self._stop_reconnect = asyncio.Event()
        self.api_initialized = False

    async def initialize_websocket(self):
        """
        Initialize the WebSocket connection and authenticate to the API
        """
        url = f"{self.websocket_url}/appsync/apprelay/relayconnect"

        try:
            session = aiohttp.ClientSession()
            self.websocket = await session.ws_connect(
                url, headers=self.headers, ssl=False
            )
            _LOGGER.info("WebSocket connection established.")

            # Start listening for messages
            asyncio.create_task(self._listen_to_websocket())
            await self.send_data(
                {
                    "data": {"relayrule": "share"},
                    "messageid": str(int(time.time())) + "000",
                    "msgtype": "init",
                    "scope": {
                        "loginsession": self.loginsession,
                        "userid": self.userid,
                    },
                }
            )

            # Send keep-alive messages every 10 seconds
            asyncio.create_task(self._keepalive_loop())
        except Exception as e:
            _LOGGER.error("Failed to establish WebSocket connection: %s", e)
            await self._schedule_reconnect()

    async def _listen_to_websocket(self):
        try:
            async for msg in self.websocket:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    status = data.get("status", -1)
                    msgtype = data.get("msgtype", None)

                    if status != 0 and msgtype in {"initk", "pingk"}:
                        await self.close_websocket()
                        await self._schedule_reconnect()
                        _LOGGER.debug(
                            "Received websocket message status %s, reconnecting...",
                            status,
                        )
                        return

                    # Used only to authenticate the websocket API
                    if msgtype == "initk":
                        _LOGGER.info("WebSocket API initialized.")
                        self.api_initialized = True
                        continue

                    # Keep-alive message response
                    if msgtype == "pingk":
                        _LOGGER.debug("WebSocket ping received.")
                        continue

                    _LOGGER.debug("WebSocket message received: %s", msg.data)
                    await self._notify_listeners(data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    _LOGGER.debug("WebSocket error: %s", msg.data)
                    break
        except Exception as e:
            _LOGGER.error("WebSocket connection lost: %s", e)
        finally:
            await self._schedule_reconnect()

    async def _keepalive_websocket(self):
        """
        Send a keep-alive message to the WebSocket server.
        """
        if self.websocket and not self.websocket.closed:
            try:
                await self.send_data(
                    {
                        "messageid": str(int(time.time())) + "000",
                        "msgtype": "ping",
                    }
                )
                _LOGGER.debug("WebSocket keep-alive sent.")
            except Exception as e:
                _LOGGER.error("Failed to send WebSocket keep-alive: %s", e)
                await self._schedule_reconnect()

    async def _keepalive_loop(self):
        while not self.websocket.closed:
            await self._keepalive_websocket()
            await asyncio.sleep(10)  # Send keep-alive every 10 seconds

    async def _notify_listeners(self, message: dict):
        """
        Notify all registered listeners with the received WebSocket message.
        """
        for listener in self._listeners:
            try:
                await listener(message)
            except Exception as e:
                _LOGGER.error("Error in WebSocket listener: %s", e)

    def add_websocket_listener(self, listener: callable):
        """
        Register a listener to receive WebSocket messages.

        :param listener: The callable to register as a listener.
        """
        self._listeners.append(listener)

    async def _schedule_reconnect(self):
        if self._reconnect_task is None:
            self._stop_reconnect.clear()
            self._reconnect_task = asyncio.create_task(self._reconnect())

    async def _reconnect(self):
        while not self._stop_reconnect.is_set():
            _LOGGER.debug("Attempting to reconnect WebSocket...")
            try:
                await self.initialize_websocket()
                _LOGGER.debug("Reconnected to WebSocket.")
                self._reconnect_task = None
                return
            except (ConnectionError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                _LOGGER.error("Reconnect failed: %s", e)
                await asyncio.sleep(10)  # Retry after 10 seconds

    async def send_data(self, data: dict):
        """
        Send a JSON-serialized dictionary to the WebSocket server.

        :param data: The dictionary to send.
        :raises ConnectionError: If the WebSocket is not connected.
        """
        if not self.websocket or self.websocket.closed:
            raise ConnectionError("WebSocket is not connected.")

        try:
            # Convert the dictionary to a JSON string
            json_data = json.dumps(data)
            await self.websocket.send_str(json_data)
            _LOGGER.debug("Sent JSON data via WebSocket: %s", json_data)
        except Exception as e:
            _LOGGER.error("Failed to send JSON data via WebSocket: %s", e)
            raise

    async def close_websocket(self):
        """
        Close the WebSocket connection and stop reconnection attempts.
        """
        self._stop_reconnect.set()
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None

        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            _LOGGER.warning("WebSocket connection closed.")
