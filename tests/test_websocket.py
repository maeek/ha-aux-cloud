"""Focused AUX Cloud tests."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientConnectionError, WSMessage, WSMsgType

import custom_components.aux_cloud.api.transports.websocket as websocket_module
from custom_components.aux_cloud.api import (
    AuxNetworkError,
    AuxServerError,
    AuxUnknownApiError,
)
from custom_components.aux_cloud.api.models import DeviceUpdate
from custom_components.aux_cloud.api.protocol.websocket import (
    validate_websocket_response,
)
from custom_components.aux_cloud.api.transports.websocket import (
    AuxCloudWebSocket,
    websocket_origin,
)


def _websocket(**kwargs) -> AuxCloudWebSocket:
    """Return a relay transport with an injected test session."""
    kwargs.setdefault("session", MagicMock(closed=False))
    return AuxCloudWebSocket(**kwargs)


async def test_websocket_send_ack_clears_pending():
    """Test websocket response tracking and ack handling."""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    websocket.websocket = MagicMock(closed=False)
    websocket._send_raw = AsyncMock()
    listener = MagicMock()

    send_task = asyncio.create_task(
        websocket._request(
            {"msgtype": "sub", "topic": "devpush"},
            expected_msgtype="subk",
            timeout=1,
            endpoint="websocket/subscribe",
        )
    )
    await asyncio.sleep(0)

    raw_payload = websocket._send_raw.await_args.args[0]
    payload = json.loads(raw_payload)
    assert payload["msgtype"] == "sub"

    websocket._listener = listener
    await websocket._handle_text_message(
        json.dumps(
            {
                "messageid": payload["messageid"],
                "msgtype": "subk",
                "status": 0,
            }
        ),
    )

    assert await send_task == {
        "messageid": payload["messageid"],
        "msgtype": "subk",
        "status": 0,
    }
    listener.assert_not_called()


async def test_websocket_correlates_concurrent_requests_out_of_order():
    """Test one reader can resolve concurrent command responses by message ID."""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    websocket.websocket = MagicMock(closed=False)
    websocket._send_raw = AsyncMock()

    first = asyncio.create_task(
        websocket._request(
            {"msgtype": "first"},
            expected_msgtype="firstk",
            timeout=1,
            endpoint="websocket/first",
        )
    )
    second = asyncio.create_task(
        websocket._request(
            {"msgtype": "second"},
            expected_msgtype="secondk",
            timeout=1,
            endpoint="websocket/second",
        )
    )
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

    assert (await first)["msgtype"] == "firstk"
    assert (await second)["msgtype"] == "secondk"
    assert websocket._pending == {}


async def test_websocket_rejects_mismatched_ack_type():
    """Test a correlated response with the wrong type fails explicitly."""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    websocket.websocket = MagicMock(closed=False)
    websocket._send_raw = AsyncMock()
    request = asyncio.create_task(
        websocket._request(
            {"msgtype": "sub"},
            expected_msgtype="subk",
            timeout=1,
            endpoint="websocket/subscribe",
        )
    )
    await asyncio.sleep(0)
    payload = json.loads(websocket._send_raw.await_args.args[0])

    await websocket._handle_text_message(
        json.dumps({"messageid": payload["messageid"], "msgtype": "unexpected"})
    )

    with pytest.raises(AuxServerError, match="Unexpected websocket response type"):
        await request


async def test_websocket_disconnect_fails_pending_request():
    """Test a dropped connection produces a fallback-compatible network error."""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    websocket.websocket = MagicMock(closed=False)
    websocket._send_raw = AsyncMock()
    request = asyncio.create_task(
        websocket._request(
            {"msgtype": "transit.opencontrol"},
            expected_msgtype="transit.opencontrolk",
            timeout=1,
            endpoint="websocket/transit.opencontrol",
        )
    )
    await asyncio.sleep(0)

    websocket._terminate_pending(AuxNetworkError("connection lost"))

    with pytest.raises(AuxNetworkError, match="connection lost"):
        await request


async def test_websocket_maps_disconnected_timeout_and_send_failures():
    """Test command failures consistently surface as network errors."""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )

    with pytest.raises(AuxNetworkError, match="not connected"):
        await websocket.async_send_opencontrol({"pwr": 1})
    with pytest.raises(AuxNetworkError, match="not connected"):
        await websocket._request(
            {"msgtype": "ping"},
            expected_msgtype="pingk",
            timeout=1,
            endpoint="websocket/ping",
        )

    websocket.websocket = MagicMock(closed=False)
    websocket._send_raw = AsyncMock()
    with pytest.raises(AuxNetworkError, match="Timed out waiting for pingk"):
        await websocket._request(
            {"msgtype": "ping"},
            expected_msgtype="pingk",
            timeout=0,
            endpoint="websocket/ping",
        )
    assert websocket._pending == {}

    websocket._send_raw = AuxCloudWebSocket._send_raw.__get__(websocket)
    websocket.websocket.send_str = AsyncMock(side_effect=ClientConnectionError())
    with pytest.raises(AuxNetworkError):
        await websocket._send_raw("{}")


async def test_websocket_request_timeout_includes_blocked_send():
    """Test backpressure cannot hang before the ACK timeout starts."""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    websocket.websocket = MagicMock(closed=False)

    async def blocked_send(_raw):
        await asyncio.Event().wait()

    websocket._send_raw = AsyncMock(side_effect=blocked_send)

    with pytest.raises(AuxNetworkError, match="Timed out waiting for pingk"):
        await websocket._request(
            {"msgtype": "ping"},
            expected_msgtype="pingk",
            timeout=0,
            endpoint="websocket/ping",
        )
    assert websocket._pending == {}


async def test_websocket_message_routing_isolates_bad_input_and_listeners(caplog):
    """Test malformed frames and listener failures cannot corrupt the reader."""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    listener = MagicMock(side_effect=RuntimeError("consumer failed"))
    websocket._listener = listener

    assert await websocket._handle_text_message("not-json") == {}
    assert await websocket._handle_text_message("[]") == {}
    message = await websocket._handle_ws_message(
        WSMessage(
            WSMsgType.TEXT,
            '{"msgtype":"push","topic":"devpush","data":{"endpointId":"1","data":{"pwr":1}}}',
            None,
        ),
    )
    assert message["msgtype"] == "push"
    assert "Error in AUX Cloud websocket listener" in caplog.text
    assert (
        await websocket._handle_ws_message(
            WSMessage(WSMsgType.BINARY, b"ignored", None)
        )
        == {}
    )
    with pytest.raises(AuxNetworkError, match="websocket closed"):
        await websocket._handle_ws_message(WSMessage(WSMsgType.CLOSED, None, None))


def test_websocket_callbacks_are_synchronous_and_typed():
    """Test the reader-facing callback cannot block acknowledgement routing."""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    listener = MagicMock()
    websocket._listener = listener
    updates = (DeviceUpdate("device1", {"pwr": 1}),)

    websocket._notify_updates(())
    websocket._notify_updates(updates)

    listener.assert_called_once_with(updates)


async def test_websocket_close_cancels_requests_but_not_injected_session():
    """Test shutdown releases pending commands without owning HA's session."""
    session = MagicMock(closed=False)
    session.close = AsyncMock()
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
        session=session,
    )
    connection = MagicMock(closed=False)
    connection.close = AsyncMock()
    websocket.websocket = connection
    pending = asyncio.get_running_loop().create_future()
    websocket._pending["1"] = (pending, "pingk")

    await websocket.async_close()

    connection.close.assert_awaited_once()
    session.close.assert_not_awaited()
    assert pending.cancelled()
    assert websocket.websocket is None
    assert websocket._session is session


def test_websocket_url_headers_and_subscription_cache():
    """Test relay URL/header normalization and invalid devices are filtered."""
    assert websocket_origin("wss://relay.example/path") == "https://relay.example"
    assert websocket_origin("relative-path") == ""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
        devices=[
            {"endpointId": "device1", "devSession": "s", "productId": "p"},
            {"friendlyName": "missing id"},
        ],
    )
    assert websocket._subscriptions == [
        {
            "devSession": "s",
            "endpointId": "device1",
            "gatewayId": "",
            "pid": "p",
        }
    ]


class _FakeWebSocketConnection:
    """Queue-backed websocket that automatically acknowledges sent messages."""

    def __init__(self) -> None:
        self.closed = False
        self.sent: list[dict] = []
        self.receive_calls = 0
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
        self.receive_calls += 1
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
    """Minimal injected aiohttp session for websocket lifecycle tests."""

    def __init__(self, websocket: _FakeWebSocketConnection) -> None:
        self.closed = False
        self.websocket = websocket
        self.connect_calls: list[tuple[str, dict]] = []

    async def ws_connect(self, url, *, headers):
        self.connect_calls.append((url, headers))
        return self.websocket


async def test_websocket_run_uses_one_reader_for_dynamic_subscriptions(monkeypatch):
    """Test live subscription and heartbeat ACKs share one receive owner."""
    monkeypatch.setattr(websocket_module, "PING_INTERVAL", 0.01)
    connection = _FakeWebSocketConnection()
    session = _FakeWebSession(connection)
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={"Origin": "https://example.com"},
        loginsession="session",
        userid="user",
        session=session,
        devices=[{"endpointId": "device1"}],
    )
    ready = asyncio.Event()
    received = []

    runner = asyncio.create_task(
        websocket.async_run(received.append, ready.set),
    )
    await asyncio.wait_for(ready.wait(), timeout=1)
    await websocket.subscribe_devices([{"endpointId": "device2"}])
    await asyncio.sleep(0.03)

    assert websocket.connected is True
    assert connection.max_active_receives == 1
    assert any(
        update.endpoint_id == "device2" for updates in received for update in updates
    )
    assert any(message["msgtype"] == "ping" for message in connection.sent)
    assert session.connect_calls[0][0].endswith("/appsync/apprelay/relayconnect")

    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner
    assert connection.closed is True


@pytest.mark.parametrize(
    "ack",
    [
        {"msgtype": "subresetk", "status": 7},
        {
            "msgtype": "subresetk",
            "status": 0,
            "data": {"devList": [{"endpointId": "device1", "status": 7}]},
        },
    ],
)
def test_websocket_subscription_rejects_failed_ack(ack):
    """Test failed subscription ACKs are surfaced to reconnect/retry callers."""
    with pytest.raises(AuxUnknownApiError):
        validate_websocket_response(ack, endpoint="websocket/subscribe")


async def test_websocket_init_rejection_is_propagated():
    """Test rejected init ACK fails the connection attempt."""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    websocket._request = AsyncMock(return_value={"msgtype": "initk", "status": 7})

    with pytest.raises(AuxUnknownApiError):
        await websocket._initialize()


async def test_websocket_rejects_malformed_ack_statuses():
    """Test non-numeric, non-success statuses fail closed for every handshake."""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    websocket._request = AsyncMock(return_value={"status": "unexpected"})

    with pytest.raises(AuxServerError, match="Invalid AUX websocket response"):
        await websocket._initialize()
    with pytest.raises(AuxServerError, match="Invalid AUX websocket response"):
        await websocket._ping()
    with pytest.raises(AuxServerError, match="Invalid AUX websocket response"):
        validate_websocket_response(
            {"status": "unexpected"}, endpoint="websocket/subscribe"
        )
    with pytest.raises(AuxServerError, match="Invalid AUX websocket response"):
        validate_websocket_response(
            {
                "status": 0,
                "data": {
                    "devList": [{"endpointId": "device1", "status": "unexpected"}]
                },
            },
            endpoint="websocket/subscribe",
        )


async def test_websocket_empty_subscription_and_reader_failures_are_explicit():
    """Test empty membership reset and both graceful/error reader exits."""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    websocket._request = AsyncMock(
        return_value={"msgtype": "subresetk", "status": 0, "data": {"devList": []}}
    )
    assert await websocket.subscribe_devices([])
    assert websocket._request.await_args.args[0]["data"]["devList"] == []

    websocket.websocket = MagicMock(closed=True)
    with pytest.raises(AuxNetworkError, match="websocket closed"):
        await websocket._read_loop()

    websocket.websocket = MagicMock(closed=False)
    websocket.websocket.receive = AsyncMock(side_effect=ClientConnectionError())
    with pytest.raises(AuxNetworkError):
        await websocket._read_loop()


async def test_rejected_subscription_is_not_published():
    """Test subscription snapshots are validated before reaching state listeners."""
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    listener = MagicMock()
    websocket._listener = listener
    websocket._request = AsyncMock(
        return_value={
            "msgtype": "subresetk",
            "status": 0,
            "data": {
                "devList": [{"endpointId": "device1", "status": 7, "data": {"pwr": 1}}]
            },
        }
    )

    with pytest.raises(AuxUnknownApiError):
        await websocket.subscribe_devices([{"endpointId": "device1"}])
    listener.assert_not_called()


async def test_websocket_connection_errors_are_mapped():
    """Test aiohttp connection failures become transport-neutral API errors."""
    session = MagicMock(closed=False)
    session.ws_connect = AsyncMock(side_effect=ClientConnectionError())
    websocket = _websocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
        session=session,
    )

    with pytest.raises(AuxNetworkError):
        await websocket._open_socket()
