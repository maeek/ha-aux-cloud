"""Focused AUX Cloud tests."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.aux_cloud.api import (
    AuxApiError,
    AuxCloudAPI,
    AuxNetworkError,
    AuxSessionExpired,
    extract_websocket_updates,
)
from custom_components.aux_cloud.api.models import AuxCredentials, DeviceUpdate
from custom_components.aux_cloud.api.session import (
    API_SERVER_URL_CN,
    API_SERVER_URL_EU,
    API_SERVER_URL_USA,
)


@pytest.fixture
def aux_api():
    """Return a new AuxCloudAPI instance."""
    return AuxCloudAPI(region="eu", session=MagicMock(closed=False))


def _api(region: str = "eu") -> AuxCloudAPI:
    """Return an API facade with an injected test session."""
    return AuxCloudAPI(region=region, session=MagicMock(closed=False))


class TestAuxCloudAPI:
    """Tests for the AuxCloudAPI class."""

    def test_init(self):
        """Test initialization with different regions."""
        api_eu = _api(region="eu")
        assert api_eu._session.url == API_SERVER_URL_EU
        assert api_eu._session.region == "eu"

        api_usa = _api(region="usa")
        assert api_usa._session.url == API_SERVER_URL_USA
        assert api_usa._session.region == "usa"

        api_cn = _api(region="cn")
        assert api_cn._session.url == API_SERVER_URL_CN
        assert api_cn._session.region == "cn"

        # Test default fallback
        api_unknown = _api(region="unknown")
        assert api_unknown._session.url == API_SERVER_URL_EU
        assert api_unknown._session.region == "unknown"

    async def test_facade_delegates_to_services(self, aux_api):
        """Test the public facade remains a thin, stable service boundary."""
        aux_api._session.login = AsyncMock(return_value=True)
        aux_api._session.loginsession = "session"
        aux_api._session.userid = "user"
        aux_api._repository.get_families = AsyncMock(return_value=[{"familyid": "1"}])
        aux_api._repository.get_devices = AsyncMock(return_value=[{"endpointId": "1"}])
        aux_api._control.set_device_params = AsyncMock(return_value={"pwr": 0})

        assert (
            await aux_api.login(AuxCredentials.email("user@example.com", "secret"))
            is None
        )
        assert aux_api.is_logged_in() is True
        assert aux_api.user_id == "user"
        assert await aux_api.get_families() == [{"familyid": "1"}]
        assert await aux_api.get_devices("family1", shared=True) == [
            {"endpointId": "1"}
        ]
        assert await aux_api.set_device_params({"endpointId": "1"}, {"pwr": 0}) == {
            "pwr": 0
        }
        device = {"productId": "unknown", "params": {"pwr": 1}}
        relay = aux_api._build_websocket_client("wss://relay.example", [device])
        assert relay.headers["Origin"] == "https://relay.example"

    async def test_websocket_url_discovery_validates_response(self, aux_api):
        """Test relay discovery only accepts a successful non-empty URL list."""
        aux_api._session.make_request = AsyncMock(
            return_value={"status": 0, "data": {"url": ["wss://relay.example/"]}}
        )
        assert await aux_api.get_websocket_urls() == ["wss://relay.example/"]

        aux_api._session.make_request.return_value = {
            "status": 7,
            "data": {"url": ["wss://ignored.example"]},
        }
        assert await aux_api.get_websocket_urls() == []

    def test_websocket_client_requires_active_identity(self, aux_api):
        """Test a relay transport cannot be built without authenticated identity."""
        with pytest.raises(AuxSessionExpired):
            aux_api._build_websocket_client("wss://relay.example", [])

    async def test_websocket_attempt_builds_fresh_transport_and_cleans_up(
        self, aux_api
    ):
        """Test each supervised attempt owns one fresh, temporary transport."""
        aux_api._session.loginsession = "session"
        aux_api._session.userid = "user"
        aux_api.get_websocket_urls = AsyncMock(
            return_value=["wss://relay.example/path/"]
        )
        transport = MagicMock()
        transport.async_run = AsyncMock()
        aux_api._build_websocket_client = MagicMock(return_value=transport)
        listener = MagicMock()
        on_ready = MagicMock()

        await aux_api.async_run_websocket(
            [{"endpointId": "device1"}], listener, on_ready
        )

        aux_api._build_websocket_client.assert_called_once_with(
            "wss://relay.example/path", [{"endpointId": "device1"}]
        )
        transport.async_run.assert_awaited_once()
        assert transport.async_run.await_args.args[0] is listener
        transport.async_run.await_args.args[1]()
        on_ready.assert_called_once()
        assert aux_api._websocket is None

    async def test_websocket_attempt_recovers_expired_session_for_next_retry(
        self, aux_api
    ):
        """Test auth expiry is recovered before the coordinator retries."""
        aux_api._session.loginsession = "expired"
        aux_api._session.userid = "user"
        aux_api.get_websocket_urls = AsyncMock(return_value=["wss://relay.example"])
        transport = MagicMock()
        transport.async_run = AsyncMock(side_effect=AuxSessionExpired())
        aux_api._build_websocket_client = MagicMock(return_value=transport)
        aux_api._session.recover_session = AsyncMock(return_value=True)

        with pytest.raises(AuxSessionExpired):
            await aux_api.async_run_websocket([])

        aux_api._session.recover_session.assert_awaited_once_with(
            expired_session="expired"
        )
        assert aux_api._websocket is None

    async def test_websocket_attempt_tries_each_relay_before_ready(self, aux_api):
        """Test discovery-provided relay failover is limited to setup failures."""
        aux_api._session.loginsession = "session"
        aux_api._session.userid = "user"
        aux_api.get_websocket_urls = AsyncMock(
            return_value=["wss://first.example", "wss://second.example"]
        )
        first = MagicMock(async_run=AsyncMock(side_effect=AuxNetworkError()))
        second = MagicMock(async_run=AsyncMock())
        aux_api._build_websocket_client = MagicMock(side_effect=[first, second])

        await aux_api.async_run_websocket([])

        assert aux_api._build_websocket_client.call_count == 2
        first.async_run.assert_awaited_once()
        second.async_run.assert_awaited_once()

    async def test_websocket_subscription_facade_hides_transport(self, aux_api):
        """Test coordinator membership updates use the API facade."""
        transport = MagicMock(connected=False)
        transport.subscribe_devices = AsyncMock()
        aux_api._websocket = transport

        await aux_api.async_update_websocket_subscriptions([])
        transport.subscribe_devices.assert_not_awaited()

        transport.connected = True
        await aux_api.async_update_websocket_subscriptions([])
        transport.subscribe_devices.assert_awaited_once_with([])

    async def test_websocket_attempt_rejects_missing_login_or_relay(self, aux_api):
        """Test precondition failures are surfaced to the reconnect supervisor."""
        with pytest.raises(AuxApiError, match="without being logged in"):
            await aux_api.async_run_websocket([])

        aux_api._session.loginsession = "session"
        aux_api._session.userid = "user"
        aux_api.get_websocket_urls = AsyncMock(return_value=[])
        with pytest.raises(AuxApiError, match="No AUX Cloud websocket relay"):
            await aux_api.async_run_websocket([])

    async def test_close_websocket_closes_active_transport(self, aux_api):
        """Test facade shutdown closes and releases the active relay transport."""
        transport = MagicMock()
        transport.async_close = AsyncMock()
        aux_api._websocket = transport

        await aux_api.close_websocket()

        transport.async_close.assert_awaited_once()
        assert aux_api._websocket is None

    def test_extract_websocket_push_payloads(self, aux_api):
        """Test extracting websocket devpush payload variants."""
        direct_payload = {"did": "device1", "pid": "pid1", "pwr": 1, "temp": 250}
        hex_payload = {"did": "device1", "envtemp": 215}

        updates = extract_websocket_updates(
            {
                "msgtype": "push",
                "topic": "devpush",
                "data": {
                    "endpointId": "device1",
                    "data": base64.b64encode(
                        json.dumps(direct_payload).encode()
                    ).decode(),
                    "payload": {
                        "data": json.dumps(hex_payload).encode().hex(),
                    },
                },
            }
        )

        assert updates == (
            DeviceUpdate("device1", direct_payload),
            DeviceUpdate("device1", hex_payload),
        )

    def test_extract_websocket_subreset_and_opencontrol(self, aux_api):
        """Test extracting subreset and transit.opencontrol websocket updates."""
        subreset_updates = extract_websocket_updates(
            {
                "msgtype": "subresetk",
                "data": {
                    "devList": [
                        {
                            "endpointId": "device1",
                            "data": {"pwr": 1, "temp": 240},
                        }
                    ]
                },
            }
        )
        assert subreset_updates == (DeviceUpdate("device1", {"pwr": 1, "temp": 240}),)

        opencontrol_updates = extract_websocket_updates(
            {
                "msgtype": "transit.opencontrolk",
                "data": {
                    "responseList": [
                        {
                            "event": {
                                "endpoint": {"endpointId": "device1"},
                                "payload": {
                                    "status": 0,
                                    "data": json.dumps(
                                        {
                                            "params": ["pwr", "temp"],
                                            "vals": [
                                                [{"idx": 1, "val": 1}],
                                                [{"idx": 1, "val": 245}],
                                            ],
                                        }
                                    ),
                                },
                            }
                        }
                    ]
                },
            }
        )
        assert opencontrol_updates == (
            DeviceUpdate("device1", {"pwr": 1, "temp": 245}),
        )

    def test_extract_websocket_offline_devlist_drops_stale_params(self):
        """Test offline websocket payloads do not expose stale retained device data."""
        updates = extract_websocket_updates(
            {
                "msgtype": "subresetk",
                "topic": "devpush",
                "data": {
                    "devList": [
                        {
                            "endpointId": "device1",
                            "status": 0,
                            "data": {
                                "online": False,
                                "state": 0,
                                "pwr": 1,
                                "temp": 245,
                            },
                        }
                    ]
                },
            }
        )

        assert updates == (DeviceUpdate("device1", {}, available=False),)
