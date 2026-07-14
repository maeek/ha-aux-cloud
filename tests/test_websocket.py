"""Behavior-focused AUX Cloud websocket tests."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import WSMessage, WSMsgType

import custom_components.aux_cloud.api.transports.websocket as websocket_module
from custom_components.aux_cloud.api import AuxNetworkError, AuxServerError
from custom_components.aux_cloud.api.transports.websocket import (
    AuxCloudWebSocket,
    websocket_origin,
)


def _websocket(**kwargs) -> AuxCloudWebSocket:
    kwargs.setdefault("session", MagicMock(closed=False))
    return AuxCloudWebSocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
        **kwargs,
    )


async def _pending_request(websocket, msgtype):
    return asyncio.create_task(
        websocket._request(
            {"msgtype": msgtype},
            expected_msgtype=f"{msgtype}k",
            timeout=1,
            endpoint=f"websocket/{msgtype}",
        )
    )


async def test_requests_correlate_out_of_order_and_fail_cleanly():
    """The single reader correlates ACKs and terminates invalid pending work."""
    websocket = _websocket()
    websocket.websocket = MagicMock(closed=False)
    websocket._send_raw = AsyncMock()
    first = await _pending_request(websocket, "first")
    second = await _pending_request(websocket, "second")
    await asyncio.sleep(0)
    payloads = [
        json.loads(call.args[0]) for call in websocket._send_raw.await_args_list
    ]

    await websocket._handle_text_message(
        json.dumps({"messageid": payloads[1]["messageid"], "msgtype": "secondk"})
    )
    await websocket._handle_text_message(
        json.dumps({"messageid": payloads[0]["messageid"], "msgtype": "firstk"})
    )
    assert [(await first)["msgtype"], (await second)["msgtype"]] == [
        "firstk",
        "secondk",
    ]

    mismatch = await _pending_request(websocket, "ping")
    await asyncio.sleep(0)
    payload = json.loads(websocket._send_raw.await_args_list[-1].args[0])
    await websocket._handle_text_message(
        json.dumps({"messageid": payload["messageid"], "msgtype": "wrong"})
    )
    with pytest.raises(AuxServerError, match="Unexpected websocket response type"):
        await mismatch

    disconnected = await _pending_request(websocket, "control")
    await asyncio.sleep(0)
    websocket._terminate_pending(AuxNetworkError("connection lost"))
    with pytest.raises(AuxNetworkError, match="connection lost"):
        await disconnected
    assert websocket._pending == {}


class _FakeWebSocketConnection:
    """Queue-backed connection that acknowledges lifecycle requests."""

    def __init__(self) -> None:
        self.closed = False
        self.sent = []
        self.active_receives = 0
        self.max_active_receives = 0
        self._messages: asyncio.Queue[WSMessage] = asyncio.Queue()

    async def send_str(self, raw_data: str) -> None:
        payload = json.loads(raw_data)
        self.sent.append(payload)
        msgtype = payload["msgtype"]
        response = {
            "messageid": payload["messageid"],
            "msgtype": {
                "init": "initk",
                "ping": "pingk",
                "sub": "subk",
                "subreset": "subresetk",
            }[msgtype],
            "status": 0,
        }
        if msgtype in {"sub", "subreset"}:
            response["data"] = {
                "devList": [
                    {**device, "status": 0, "data": {"pwr": 1}}
                    for device in payload.get("data", {}).get("devList", [])
                ]
            }
        await self._messages.put(WSMessage(WSMsgType.TEXT, json.dumps(response), None))

    async def receive(self) -> WSMessage:
        self.active_receives += 1
        self.max_active_receives = max(self.max_active_receives, self.active_receives)
        try:
            return await self._messages.get()
        finally:
            self.active_receives -= 1

    async def close(self) -> None:
        self.closed = True
        await self._messages.put(WSMessage(WSMsgType.CLOSED, None, None))


class _FakeWebSession:
    def __init__(self, websocket) -> None:
        self.closed = False
        self.websocket = websocket
        self.connect_calls = []

    async def ws_connect(self, url, *, headers):
        self.connect_calls.append((url, headers))
        return self.websocket


async def test_relay_lifecycle_uses_one_reader_and_refreshes_membership(monkeypatch):
    """Init, subscription resets, heartbeat and shutdown share one receive owner."""
    monkeypatch.setattr(websocket_module, "PING_INTERVAL", 0.01)
    connection = _FakeWebSocketConnection()
    session = _FakeWebSession(connection)
    websocket = _websocket(
        session=session,
        devices=[{"endpointId": "device1"}],
    )
    ready = asyncio.Event()
    received = []
    runner = asyncio.create_task(websocket.async_run(received.append, ready.set))
    await asyncio.wait_for(ready.wait(), timeout=1)
    await websocket.subscribe_devices([{"endpointId": "device2"}])
    await asyncio.sleep(0.03)

    assert connection.max_active_receives == 1
    assert any(
        update.endpoint_id == "device2" for updates in received for update in updates
    )
    assert any(message["msgtype"] == "ping" for message in connection.sent)
    assert session.connect_calls[0][0].endswith("/appsync/apprelay/relayconnect")
    assert websocket_origin("wss://relay.example/path") == "https://relay.example"

    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner
    assert connection.closed is True
