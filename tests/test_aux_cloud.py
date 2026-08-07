"""Tests for the AuxCloudAPI class."""

import base64
import json
from unittest.mock import MagicMock, AsyncMock

import pytest

from custom_components.aux_cloud.api.aux_cloud import (
    AuxApiError,
    AuxCloudAPI,
    API_SERVER_URL_EU,
    API_SERVER_URL_USA,
    API_SERVER_URL_CN,
    MAX_ACT_DEVICE_RETRIES,
)


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


@pytest.fixture
def mock_device():
    """Return a minimal device dict accepted by _act_device_params."""
    cookie = base64.b64encode(
        json.dumps({"terminalid": "term1", "aeskey": "key1"}).encode()
    ).decode()
    return {
        "endpointId": "device1",
        "productId": "000000000000000000000000c0620000",
        "cookie": cookie,
        "devSession": "session1",
        "mac": "00:00:00:00:00:00",
        "devicetypeFlag": 0,
    }


def _error_response(error_type: str) -> dict:
    return {
        "event": {
            "header": {"name": "ErrorResponse"},
            "payload": {"type": error_type, "message": "endpoint unreachable"},
        }
    }


def _success_response(params: dict) -> dict:
    return {
        "event": {
            "header": {"name": "Response"},
            "payload": {
                "data": json.dumps(
                    {
                        "params": list(params.keys()),
                        "vals": [[{"val": v}] for v in params.values()],
                    }
                )
            },
        }
    }


class TestAuxCloudApiRetry:
    """Tests for the retry-on-transient-network-timeout behavior."""

    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        """Avoid real delays between retries in tests."""
        monkeypatch.setattr(
            "custom_components.aux_cloud.api.aux_cloud.asyncio.sleep",
            AsyncMock(return_value=None),
        )

    async def test_retries_on_network_timeout_then_succeeds(self, aux_api, mock_device):
        """A transient NETWORK_TIME_OUT should be retried and can still succeed."""
        aux_api._make_request = AsyncMock(
            side_effect=[
                _error_response("NETWORK_TIME_OUT"),
                _error_response("NETWORK_TIME_OUT"),
                _success_response({"temp": 238}),
            ]
        )

        result = await aux_api.set_device_params(mock_device, {"temp": 238})

        assert result == {"temp": 238}
        assert aux_api._make_request.call_count == 3

    async def test_gives_up_after_max_retries(self, aux_api, mock_device):
        """Persistent NETWORK_TIME_OUT errors should eventually raise."""
        aux_api._make_request = AsyncMock(
            return_value=_error_response("NETWORK_TIME_OUT")
        )

        with pytest.raises(AuxApiError):
            await aux_api.set_device_params(mock_device, {"temp": 238})

        assert aux_api._make_request.call_count == MAX_ACT_DEVICE_RETRIES + 1

    async def test_non_retryable_error_fails_immediately(self, aux_api, mock_device):
        """A non-timeout error should not be retried."""
        aux_api._make_request = AsyncMock(
            return_value=_error_response("SOME_OTHER_ERROR")
        )

        with pytest.raises(AuxApiError):
            await aux_api.set_device_params(mock_device, {"temp": 238})

        assert aux_api._make_request.call_count == 1
