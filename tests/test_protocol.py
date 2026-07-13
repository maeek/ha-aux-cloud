"""Focused AUX Cloud tests."""

import base64
import json

import pytest

from custom_components.aux_cloud.api import (
    AuxAuthError,
    AuxDeviceError,
    AuxNetworkError,
    AuxRateLimitError,
    AuxServerError,
    AuxSessionExpired,
    AuxUnknownApiError,
)
from custom_components.aux_cloud.api.errors import (
    extract_error_code,
    parse_retry_after,
    raise_for_cloud_response,
    raise_for_http_status,
)
from custom_components.aux_cloud.api.protocol.common import (
    build_device_params_directive,
    decode_device_cookie,
    parse_control_event,
    parse_std_data,
)
from custom_components.aux_cloud.api.transports.websocket import (
    websocket_connect_url,
)

from .api_helpers import mock_cookie as _mock_cookie
from .api_helpers import mock_device as _mock_device


class TestAuxCloudAPI:
    """Tests for the AuxCloudAPI class."""

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

        with pytest.raises(AuxServerError):
            parse_control_event(
                {
                    "header": {"name": "Unexpected"},
                    "payload": {"status": 0, "data": data},
                }
            )

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

    @pytest.mark.parametrize(
        ("status", "error_type"),
        [
            (401, AuxSessionExpired),
            (429, AuxRateLimitError),
            (408, AuxNetworkError),
            (418, AuxUnknownApiError),
        ],
    )
    def test_http_error_decoder_covers_each_status_family(self, status, error_type):
        """Test every HTTP status family maps to its distinct retry behavior."""
        with pytest.raises(error_type) as raised:
            raise_for_http_status(status, endpoint="test", retry_after="7")
        if status == 429:
            assert raised.value.retry_after == 7

    def test_nested_error_and_retry_after_edge_cases(self):
        """Test nested relay errors and date-form retry hints are decoded safely."""
        assert extract_error_code(None) is None
        assert extract_error_code({"status": True}) is None
        assert (
            extract_error_code(
                {"data": {"responseList": [{"event": {"payload": {"code": -7}}}]}}
            )
            == -7
        )
        assert parse_retry_after(None) is None
        assert parse_retry_after("Wed, 21 Oct 2015 07:28:00") == 1

    def test_malformed_cookie_and_control_payloads_fail_closed(self):
        """Test bounded cookie parsing never guesses missing control metadata."""
        assert decode_device_cookie(None) is None
        assert decode_device_cookie("not-base64") is None
        assert decode_device_cookie(base64.b64encode(b"[]").decode()) is None
        assert parse_std_data(None) == {}
        assert parse_std_data("[]") == {}
        assert parse_std_data({"params": ["pwr"], "vals": []}) == {}

        with pytest.raises(ValueError):
            build_device_params_directive(_mock_device(), "set", ["pwr"], [])
        malformed = _mock_device()
        malformed["cookie"] = _mock_cookie(aeskey="")
        with pytest.raises(AuxDeviceError):
            build_device_params_directive(malformed, "get")
        missing = _mock_device()
        missing.pop("mac")
        with pytest.raises(AuxDeviceError):
            build_device_params_directive(missing, "get")

        with pytest.raises(AuxServerError):
            parse_control_event({"header": {"name": "Response"}, "payload": []})
        with pytest.raises(AuxServerError):
            parse_control_event(
                {"header": {"name": "Response"}, "payload": {"data": "["}}
            )

    def test_websocket_connect_url_does_not_duplicate_relay_path(self):
        """Test relay discovery URLs may be base hosts or full connect URLs."""
        assert websocket_connect_url("wss://example.com") == (
            "wss://example.com/appsync/apprelay/relayconnect"
        )
        assert (
            websocket_connect_url("wss://example.com/appsync/apprelay/relayconnect")
            == "wss://example.com/appsync/apprelay/relayconnect"
        )
        assert (
            websocket_connect_url("wss://example.com/appsync/apprelay/relayconnect/")
            == "wss://example.com/appsync/apprelay/relayconnect"
        )
