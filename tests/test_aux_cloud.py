"""Tests for the AuxCloudAPI class."""

import asyncio
import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

import custom_components.aux_cloud.api.session as session_module
from custom_components.aux_cloud.api import (
    AuxApiError,
    AuxAuthError,
    AuxCloudAPI,
    AuxDeviceError,
    AuxNetworkError,
    AuxRateLimitError,
    AuxServerError,
    AuxSessionExpired,
    AuxUnknownApiError,
    AuxWebSocketState,
    extract_websocket_updates,
)
from custom_components.aux_cloud.api.client import AuxCloudAPI as ClientAuxCloudAPI
from custom_components.aux_cloud.api.errors import (
    config_flow_error_key,
    raise_for_cloud_response,
    raise_for_http_status,
)
from custom_components.aux_cloud.api.protocol.common import parse_std_data
from custom_components.aux_cloud.api.repository import AuxCloudRepository
from custom_components.aux_cloud.api.session import (
    API_SERVER_URL_CN,
    API_SERVER_URL_EU,
    API_SERVER_URL_USA,
    AuxCloudSession,
)
from custom_components.aux_cloud.api.transports.http import parse_control_event
from custom_components.aux_cloud.api.transports.websocket import (
    AuxCloudWebSocket,
    AuxCloudWebSocket as TransportAuxCloudWebSocket,
    websocket_connect_url,
)
from custom_components.aux_cloud.config_flow import _async_fetch_family_devices
from custom_components.aux_cloud.devices.normalizers import normalize_device_params
from custom_components.aux_cloud.devices.profiles import (
    AC_MODE_SPECIAL,
    AC_POWER,
    HP_HOT_WATER_TANK_TEMPERATURE,
    AuxProducts,
    initial_param_queries,
    prepare_command,
)


def _decrypt_test_login_payload(call_args) -> dict:
    """Return the JSON login payload captured from a mocked request."""
    return json.loads(call_args.kwargs["data_raw"].decode())


@pytest.fixture
def aux_api():
    """Return a new AuxCloudAPI instance."""
    return AuxCloudAPI(region="eu")


@pytest.fixture
def mock_response():
    """Return a mock response for API calls."""
    mock = MagicMock()
    mock.status = 200
    mock.text = AsyncMock(return_value='{"status": 0, "data": {}}')
    return mock


class TestAuxCloudAPI:
    """Tests for the AuxCloudAPI class."""

    def test_init(self):
        """Test initialization with different regions."""
        api_eu = AuxCloudAPI(region="eu")
        assert api_eu.url == API_SERVER_URL_EU
        assert api_eu.region == "eu"

        api_usa = AuxCloudAPI(region="usa")
        assert api_usa.url == API_SERVER_URL_USA
        assert api_usa.region == "usa"

        api_cn = AuxCloudAPI(region="cn")
        assert api_cn.url == API_SERVER_URL_CN
        assert api_cn.region == "cn"

        # Test default fallback
        api_unknown = AuxCloudAPI(region="unknown")
        assert api_unknown.url == API_SERVER_URL_EU
        assert api_unknown.region == "unknown"

    def test_get_headers(self, aux_api):
        """Test the headers' generation."""
        # Basic headers
        headers = aux_api._get_headers()
        assert "Content-Type" in headers
        assert headers["loginsession"] == ""
        assert headers["userid"] == ""

        # With login session and user ID
        aux_api.loginsession = "test_session"
        aux_api.userid = "test_user"
        headers = aux_api._get_headers()
        assert headers["loginsession"] == "test_session"
        assert headers["userid"] == "test_user"

        # With additional kwargs
        headers = aux_api._get_headers(custom_header="custom_value")
        assert headers["custom_header"] == "custom_value"

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

        assert updates == [
            {"endpointId": "device1", "params": direct_payload, "status": 0},
            {"endpointId": "device1", "params": hex_payload, "status": 0},
        ]

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
        assert subreset_updates == [
            {"endpointId": "device1", "params": {"pwr": 1, "temp": 240}, "status": 0}
        ]

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
        assert opencontrol_updates == [
            {"endpointId": "device1", "params": {"pwr": 1, "temp": 245}, "status": 0}
        ]

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

        assert updates == [
            {
                "endpointId": "device1",
                "params": {},
                "status": 0,
                "available": False,
            }
        ]

    def test_http_control_event_uses_shared_std_parser(self):
        """Test HTTP strategy parses control events with the shared stdData parser."""
        data = json.dumps(
            {"params": ["pwr", "temp"], "vals": [[{"val": 1}], [{"val": 245}]]}
        )
        assert parse_std_data(data) == {"pwr": 1, "temp": 245}
        assert parse_control_event(
            {
                "header": {"name": "Response"},
                "payload": {"status": 0, "data": data},
            }
        ) == {"pwr": 1, "temp": 245}

    def test_error_decoder_maps_cloud_and_http_failures(self):
        """Test documented AUX/BroadLink errors map to typed exceptions."""
        with pytest.raises(AuxAuthError):
            raise_for_cloud_response({"status": -1006}, endpoint="account/login")

        with pytest.raises(AuxSessionExpired):
            raise_for_cloud_response({"status": -1000}, endpoint="device/query")

        with pytest.raises(AuxNetworkError):
            raise_for_cloud_response({"status": -3004}, endpoint="device/query")

        with pytest.raises(AuxServerError):
            raise_for_cloud_response({"status": -49002}, endpoint="device/query")

        with pytest.raises(AuxServerError):
            raise_for_http_status(503, endpoint="device/query")

        assert (
            str(AuxDeviceError(code=-3, endpoint="device/control/v2/sdkcontrol"))
            == "AUX Cloud device is unavailable "
            "(code -3, endpoint device/control/v2/sdkcontrol)"
        )

    def test_config_flow_error_keys_use_typed_errors(self):
        """Test typed AUX errors map to stable config-flow translation keys."""
        assert config_flow_error_key(AuxAuthError(code=-1006)) == "bad_credentials"
        assert config_flow_error_key(AuxSessionExpired(code=-1000)) == "session_expired"
        assert (
            config_flow_error_key(AuxServerError(http_status=503)) == "api_unavailable"
        )

    async def test_config_flow_device_discovery_keeps_successful_query(self):
        """Test one failed device query does not hide sibling devices."""

        class FakeCloud:
            async def get_devices(self, family_id, shared=False):
                assert family_id == "family1"
                if shared:
                    raise AuxServerError(http_status=503)
                return [{"endpointId": "device1"}]

        devices, errors, successful_queries = await _async_fetch_family_devices(
            FakeCloud(), "family1"
        )

        assert devices == [{"endpointId": "device1"}]
        assert len(errors) == 1
        assert isinstance(errors[0], AuxServerError)
        assert successful_queries == 1

    async def test_config_flow_device_discovery_deduplicates_endpoint_ids(self):
        """Test duplicate personal/shared devices keep the first result."""

        class FakeCloud:
            async def get_devices(self, family_id, shared=False):
                assert family_id == "family1"
                if shared:
                    return [
                        {"endpointId": "device1", "source": "shared"},
                        {"endpointId": "device2", "source": "shared"},
                    ]
                return [{"endpointId": "device1", "source": "personal"}]

        devices, errors, successful_queries = await _async_fetch_family_devices(
            FakeCloud(), "family1"
        )

        assert devices == [
            {"endpointId": "device1", "source": "personal"},
            {"endpointId": "device2", "source": "shared"},
        ]
        assert errors == []
        assert successful_queries == 2

    async def test_config_flow_device_discovery_tracks_all_query_failures(self):
        """Test full cloud-query failure is distinguishable from no devices."""

        class FakeCloud:
            async def get_devices(self, family_id, shared=False):
                raise AuxServerError(http_status=503)

        devices, errors, successful_queries = await _async_fetch_family_devices(
            FakeCloud(), "family1"
        )

        assert devices == []
        assert len(errors) == 2
        assert successful_queries == 0

    async def test_config_flow_device_discovery_reraises_auth_errors(self):
        """Test auth-wide discovery failures still abort immediately."""

        class FakeCloud:
            async def get_devices(self, family_id, shared=False):
                raise AuxAuthError(code=-1006)

        with pytest.raises(AuxAuthError):
            await _async_fetch_family_devices(FakeCloud(), "family1")

    async def test_websocket_url_discovery_does_not_use_static_relay_fallback(
        self, aux_api
    ):
        """Test failed websocket discovery lets coordinator degrade to HTTP fallback."""
        aux_api._make_request = AsyncMock(return_value={"status": 1, "data": {}})

        assert await aux_api.get_websocket_urls() == []

    def test_websocket_connect_url_does_not_duplicate_relay_path(self):
        """Test relay discovery URLs may be base hosts or full connect URLs."""
        assert websocket_connect_url("wss://example.com") == (
            "wss://example.com/appsync/apprelay/relayconnect"
        )
        assert websocket_connect_url(
            "wss://example.com/appsync/apprelay/relayconnect"
        ) == "wss://example.com/appsync/apprelay/relayconnect"
        assert websocket_connect_url(
            "wss://example.com/appsync/apprelay/relayconnect/"
        ) == "wss://example.com/appsync/apprelay/relayconnect"

    async def test_email_login_payload_remains_email_payload(self, monkeypatch):
        """Test legacy email login still sends the original email-shaped payload."""
        session = AuxCloudSession()
        session.make_request = AsyncMock(
            return_value={"status": 0, "loginsession": "session", "userid": "user"}
        )
        monkeypatch.setattr(
            session_module,
            "encrypt_aes_cbc_zero_padding",
            lambda _iv, _key, data: data,
        )

        assert await session.login("user@example.com", "secret") is True

        payload = _decrypt_test_login_payload(session.make_request.call_args)
        assert list(payload) == ["email", "password", "companyid", "lid"]
        assert payload["email"] == "user@example.com"
        assert "username" not in payload
        assert session.email == "user@example.com"
        assert session.phone_number is None

    async def test_phone_login_payload_uses_username_and_country_code(
        self, monkeypatch
    ):
        """Test phone login sends the phone-specific username payload."""
        session = AuxCloudSession(region="cn")
        session.make_request = AsyncMock(
            return_value={"status": 0, "loginsession": "session", "userid": "user"}
        )
        monkeypatch.setattr(
            session_module,
            "encrypt_aes_cbc_zero_padding",
            lambda _iv, _key, data: data,
        )

        assert (
            await session.login(
                password="secret",
                phone_number="13800138000",
            )
            is True
        )

        payload = _decrypt_test_login_payload(session.make_request.call_args)
        assert payload["username"] == "13800138000"
        assert payload["countrycode"] == ""
        assert "email" not in payload
        assert session.email is None
        assert session.phone_number == "13800138000"

    async def test_phone_login_payload_sends_user_entered_number(self, monkeypatch):
        """Test phone login can send the user-entered number."""
        session = AuxCloudSession(region="eu")
        session.make_request = AsyncMock(
            return_value={"status": 0, "loginsession": "session", "userid": "user"}
        )
        monkeypatch.setattr(
            session_module,
            "encrypt_aes_cbc_zero_padding",
            lambda _iv, _key, data: data,
        )

        assert (
            await session.login(
                password="secret",
                phone_number="48123456789",
            )
            is True
        )

        payload = _decrypt_test_login_payload(session.make_request.call_args)
        assert payload["username"] == "48123456789"
        assert payload["countrycode"] == ""
        assert session.phone_number == "48123456789"

    async def test_session_recovery_relogs_in_and_retries_request(self):
        """Test expired sessions trigger one silent credential re-login."""
        session = AuxCloudSession()
        session.email = "user@example.com"
        session.password = "secret"
        calls = []

        async def request_once(*args, **kwargs):
            endpoint = kwargs["endpoint"]
            calls.append(endpoint)
            if endpoint == "account/login":
                return {"status": 0, "loginsession": "new-session", "userid": "user"}
            if calls.count("appsync/group/member/getfamilylist") == 1:
                raise AuxSessionExpired(code=-1000, endpoint=endpoint)
            return {"status": 0, "data": {"ok": True}}

        session._request_once = AsyncMock(side_effect=request_once)

        result = await session.make_request(
            method="POST",
            endpoint="appsync/group/member/getfamilylist",
        )

        assert result == {"status": 0, "data": {"ok": True}}
        assert session.loginsession == "new-session"
        assert calls == [
            "appsync/group/member/getfamilylist",
            "account/login",
            "appsync/group/member/getfamilylist",
        ]

    async def test_session_recovery_bad_credentials_raises_auth_error(self):
        """Test failed silent re-login surfaces an auth-specific error."""
        session = AuxCloudSession()
        session.email = "user@example.com"
        session.password = "secret"

        async def request_once(*args, **kwargs):
            endpoint = kwargs["endpoint"]
            if endpoint == "account/login":
                return {"status": -1006}
            raise AuxSessionExpired(code=-1000, endpoint=endpoint)

        session._request_once = AsyncMock(side_effect=request_once)

        with pytest.raises(AuxAuthError):
            await session.make_request(method="POST", endpoint="device/query")

    async def test_phone_session_recovery_uses_phone_credentials(self):
        """Test silent recovery preserves phone credentials."""
        session = AuxCloudSession(region="cn")
        session.phone_number = "13800138000"
        session.password = "secret"
        session.login = AsyncMock(return_value=True)

        assert await session.recover_session() is True

        session.login.assert_awaited_once_with(
            password="secret",
            phone_number="13800138000",
        )

    async def test_websocket_auth_refresh_uses_session_recovery(self, aux_api):
        """Test websocket auth refresh uses the shared session recovery path."""
        aux_api.email = "user@example.com"
        aux_api.password = "secret"
        aux_api.loginsession = "old-session"
        aux_api.userid = "old-user"

        async def recover_session():
            aux_api.loginsession = "new-session"
            aux_api.userid = "new-user"
            return True

        aux_api.session.recover_session = AsyncMock(side_effect=recover_session)

        auth_data = await aux_api._refresh_websocket_auth("wss://example.com")

        aux_api.session.recover_session.assert_awaited_once()
        assert auth_data["loginsession"] == "new-session"
        assert auth_data["userid"] == "new-user"
        assert auth_data["headers"]["loginsession"] == "new-session"

    def test_api_package_exports_home_assistant_surface(self):
        """Test the package API exposes the HA-facing surface."""
        assert AuxCloudAPI is ClientAuxCloudAPI
        assert AuxCloudWebSocket is TransportAuxCloudWebSocket
        assert AuxApiError
        assert AuxAuthError
        assert AuxDeviceError
        assert AuxNetworkError
        assert AuxRateLimitError
        assert AuxServerError
        assert AuxSessionExpired
        assert AuxUnknownApiError
        assert AuxWebSocketState.READY
        assert AC_POWER in AuxProducts.get_params_list(_mock_device()["productId"])

    def test_ac_profile_initial_queries_and_supported_params(self):
        """Test AC profile exposes bootstrap and entity capability params."""
        device = _mock_device()

        assert initial_param_queries(device) == [[], [AC_MODE_SPECIAL]]
        assert AC_POWER in AuxProducts.get_params_list(device["productId"])
        assert AuxProducts.get_special_params_list(device["productId"]) == [
            AC_MODE_SPECIAL
        ]

    def test_heat_pump_profile_initial_queries(self):
        """Test heat-pump profile owns v2/v3 bootstrap query differences."""
        assert initial_param_queries(_mock_heat_pump(ver=2)) == [
            [],
            [HP_HOT_WATER_TANK_TEMPERATURE],
        ]
        assert initial_param_queries(_mock_heat_pump(ver=3)) == [["ver"]]

    def test_v3_heat_pump_prepare_command_appends_version_marker(self):
        """Test v3 heat-pump command preparation appends AUX version marker."""
        params, vals = prepare_command(
            _mock_heat_pump(ver=3),
            "set",
            ["hp_pwr"],
            [[{"idx": 1, "val": 1}]],
        )

        assert params == ["hp_pwr", "ver"]
        assert vals[-1] == [{"idx": 1, "val": 3}]

    def test_v3_heat_pump_tank_temperature_normalizer(self):
        """Test v3 heat-pump key_states tank temperature normalization."""
        device = _mock_heat_pump(ver=3)
        device["params"] = {"key_states": "000044"}

        normalize_device_params(device)

        assert device["params"][HP_HOT_WATER_TANK_TEMPERATURE] == 360

    async def test_repository_bootstraps_devices_from_product_profile(self):
        """Test repository uses product profiles for initial param queries."""
        device = _mock_device()

        class FakeSession:
            userid = "user"

            def get_headers(self, **kwargs):
                return kwargs

            async def make_request(self, **kwargs):
                endpoint = kwargs["endpoint"]
                if "dev/query" in endpoint:
                    return {"status": 0, "data": {"endpoints": [device]}}
                if endpoint == "device/control/v2/querystate":
                    return {
                        "event": {
                            "payload": {
                                "status": 0,
                                "data": [{"did": "device1", "state": 1}],
                            }
                        }
                    }
                raise AssertionError(endpoint)

        class FakeControl:
            def __init__(self):
                self.queries = []

            async def get_device_params(self, queried_device, params=None):
                self.queries.append(params)
                return {"pwr": 1} if params == [] else {"mode": 4}

        control = FakeControl()
        repository = AuxCloudRepository(FakeSession(), control)

        devices = await repository.get_devices("family1")

        assert control.queries == [[], [AC_MODE_SPECIAL]]
        assert devices[0]["params"] == {"pwr": 1, "mode": 4}

    async def test_repository_skips_initial_params_for_offline_devices(self):
        """Test offline devices do not issue sdkcontrol bootstrap queries."""
        device = _mock_device()

        class FakeSession:
            userid = "user"

            def get_headers(self, **kwargs):
                return kwargs

            async def make_request(self, **kwargs):
                endpoint = kwargs["endpoint"]
                if "dev/query" in endpoint:
                    return {"status": 0, "data": {"endpoints": [device]}}
                if endpoint == "device/control/v2/querystate":
                    return {
                        "event": {
                            "payload": {
                                "status": 0,
                                "data": [{"did": "device1", "state": 0}],
                            }
                        }
                    }
                raise AssertionError(endpoint)

        class FakeControl:
            def __init__(self):
                self.queries = []

            async def get_device_params(self, queried_device, params=None):
                self.queries.append(params)
                raise AssertionError("offline device should not be queried")

        control = FakeControl()
        repository = AuxCloudRepository(FakeSession(), control)

        devices = await repository.get_devices("family1")

        assert control.queries == []
        assert devices[0]["state"] == 0
        assert devices[0]["params"] == {}

    async def test_repository_keeps_primary_params_when_special_query_fails(self):
        """Test special-param failures do not discard primary params."""
        device = _mock_device()
        repository = AuxCloudRepository(_FakeRepositorySession(device), None)
        repository._control = _FakeInitialParamsControl(
            {
                (): {"pwr": 1},
                (AC_MODE_SPECIAL,): ValueError("special failed"),
            }
        )

        devices = await repository.get_devices("family1")

        assert devices[0]["params"] == {"pwr": 1}
        assert "last_updated" in devices[0]

    async def test_repository_keeps_special_params_when_primary_query_fails(self):
        """Test primary-param failures do not discard special params."""
        device = _mock_device()
        repository = AuxCloudRepository(_FakeRepositorySession(device), None)
        repository._control = _FakeInitialParamsControl(
            {
                (): ValueError("primary failed"),
                (AC_MODE_SPECIAL,): {"mode": 4},
            }
        )

        devices = await repository.get_devices("family1")

        assert devices[0]["params"] == {"mode": 4}
        assert "last_updated" in devices[0]

    async def test_repository_logs_all_initial_param_failures(self, caplog):
        """Test complete param query failure leaves params empty and logs details."""
        device = _mock_device()
        repository = AuxCloudRepository(_FakeRepositorySession(device), None)
        repository._control = _FakeInitialParamsControl(
            {
                (): ValueError("primary failed"),
                (AC_MODE_SPECIAL,): ValueError("special failed"),
            }
        )

        devices = await repository.get_devices("family1")

        assert devices[0]["params"] == {}
        assert "last_updated" not in devices[0]
        assert "primary failed" in caplog.text
        assert "special failed" in caplog.text

    async def test_set_device_params_uses_websocket_first(self, aux_api):
        """Test websocket command payload generation and response parsing."""
        device = _mock_device()

        class FakeWebSocket:
            connected = True

            def __init__(self):
                self.sent_data = None

            async def async_send_opencontrol(self, data, timeout=10):
                self.sent_data = data
                return {
                    "status": 0,
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
                                                "params": ["pwr"],
                                                "vals": [[{"idx": 1, "val": 1}]],
                                            }
                                        ),
                                    },
                                }
                            }
                        ]
                    },
                }

        fake_ws = FakeWebSocket()
        aux_api.ws_api = fake_ws
        aux_api.loginsession = "session"
        aux_api.userid = "user"

        result = await aux_api.set_device_params(device, {"pwr": 1})

        assert result == {"pwr": 1}
        assert fake_ws.sent_data["header"]["loginsession"] == "session"
        assert fake_ws.sent_data["bodyList"][0]["directive"]["payload"]["act"] == "set"
        assert fake_ws.sent_data["bodyList"][0]["directive"]["payload"]["params"] == [
            "pwr"
        ]

    async def test_set_device_params_falls_back_to_http(self, aux_api):
        """Test HTTP fallback when websocket command fails."""
        device = _mock_device()

        class FailingWebSocket:
            connected = True

            async def async_send_opencontrol(self, data, timeout=10):
                raise TimeoutError

        aux_api.ws_api = FailingWebSocket()
        aux_api.http_strategy.act_device_params = AsyncMock(return_value={"pwr": 1})

        result = await aux_api.set_device_params(device, {"pwr": 1})

        assert result == {"pwr": 1}
        aux_api.http_strategy.act_device_params.assert_awaited_once()


async def test_websocket_reliable_send_ack_clears_pending():
    """Test websocket reliable message tracking and ack handling."""
    websocket = AuxCloudWebSocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    websocket.websocket = MagicMock(closed=False)
    websocket._send_raw = AsyncMock()

    send_task = asyncio.create_task(
        websocket.send_data(
            {"msgtype": "sub", "topic": "devpush"},
            reliable=True,
            wait_response=True,
            timeout=1,
        )
    )
    await asyncio.sleep(0)

    raw_payload = websocket._send_raw.await_args.args[0]
    payload = json.loads(raw_payload)
    assert payload["msgtype"] == "sub"

    await websocket._handle_text_message(
        json.dumps(
            {
                "messageid": payload["messageid"],
                "msgtype": "subk",
                "status": 0,
            }
        )
    )

    assert await send_task == {
        "messageid": payload["messageid"],
        "msgtype": "subk",
        "status": 0,
    }


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
    with pytest.raises(ConnectionError):
        AuxCloudWebSocket._validate_subscription_response(ack)


async def test_websocket_emits_state_changes():
    """Test websocket state callback emits only changed states."""
    websocket = AuxCloudWebSocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    states = []

    await websocket._emit_state(AuxWebSocketState.CONNECTING, states.append)
    await websocket._emit_state(AuxWebSocketState.CONNECTING, states.append)
    await websocket._emit_state(AuxWebSocketState.READY, states.append)

    assert states == [AuxWebSocketState.CONNECTING, AuxWebSocketState.READY]


async def test_websocket_init_rejection_marks_auth_failed():
    """Test rejected init ACK fails the connection attempt."""
    websocket = AuxCloudWebSocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    websocket._open_socket = AsyncMock()
    websocket._send_and_wait = AsyncMock(return_value={"msgtype": "initk", "status": 7})

    with pytest.raises(ConnectionError):
        await websocket._connect_and_subscribe(None)

    assert websocket._auth_failed is True


async def test_websocket_ping_timeout_raises():
    """Test app-level ping timeout fails the active connection."""
    websocket = AuxCloudWebSocket(
        websocket_url="wss://example.com",
        headers={},
        loginsession="session",
        userid="user",
    )
    websocket._send_and_wait = AsyncMock(side_effect=TimeoutError)

    with pytest.raises(TimeoutError):
        await websocket._ping(None)


def test_error_reporting_translation_keys_exist():
    """Test all error reporting translation keys exist in bundled languages."""
    translation_dir = (
        Path(__file__).parents[1] / "custom_components" / "aux_cloud" / "translations"
    )
    config_error_keys = {
        "bad_credentials",
        "session_expired",
        "api_unavailable",
        "rate_limited",
        "cannot_connect",
        "unknown",
    }
    issue_keys = {"api_unavailable", "auth_failed", "rate_limited"}
    exception_keys = {
        "api_unavailable",
        "cannot_connect",
        "device_error",
        "invalid_auth",
        "rate_limited",
        "session_expired",
        "unknown",
    }

    for language in ("en", "pl", "el"):
        translations = json.loads((translation_dir / f"{language}.json").read_text())
        assert config_error_keys <= set(translations["config"]["error"])
        assert config_error_keys <= set(translations["config"]["abort"])
        assert issue_keys <= set(translations["issues"])
        assert exception_keys <= set(translations["exceptions"])


def _mock_device():
    """Return a minimal mock device for command tests."""
    cookie = base64.b64encode(
        json.dumps({"terminalid": 1234, "aeskey": "key"}).encode()
    ).decode()
    return {
        "endpointId": "device1",
        "friendlyName": "AC Unit 1",
        "productId": "000000000000000000000000c0620000",
        "devSession": "dev-session",
        "devicetypeFlag": 1,
        "mac": "aa:bb:cc:dd:ee:ff",
        "cookie": cookie,
        "familyId": "family1",
    }


def _mock_heat_pump(ver: int = 3):
    """Return a minimal mock heat-pump device."""
    device = _mock_device()
    device["productId"] = "000000000000000000000000c3aa0000"
    device["friendlyName"] = "Heat Pump"
    device["extern"] = json.dumps({"ver": ver})
    return device


class _FakeRepositorySession:
    """Fake session for repository bootstrap tests."""

    userid = "user"

    def __init__(self, device: dict) -> None:
        self._device = device

    def get_headers(self, **kwargs):
        """Return passed headers."""
        return kwargs

    async def make_request(self, **kwargs):
        """Return canned repository responses."""
        endpoint = kwargs["endpoint"]
        if "dev/query" in endpoint:
            return {"status": 0, "data": {"endpoints": [self._device]}}
        if endpoint == "device/control/v2/querystate":
            return {
                "event": {
                    "payload": {
                        "status": 0,
                        "data": [{"did": "device1", "state": 1}],
                    }
                }
            }
        raise AssertionError(endpoint)


class _FakeInitialParamsControl:
    """Fake control service for initial parameter query tests."""

    def __init__(self, query_results: dict[tuple[str, ...], dict | Exception]) -> None:
        self._query_results = query_results

    async def get_device_params(self, queried_device, params=None):
        """Return or raise the result configured for a query."""
        result = self._query_results[tuple(params or [])]
        if isinstance(result, Exception):
            raise result
        return result
