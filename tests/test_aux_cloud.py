"""Tests for the AuxCloudAPI class."""

from unittest.mock import MagicMock, AsyncMock

import pytest

from custom_components.aux_cloud.api.aux_cloud import (
    AuxCloudAPI,
    API_SERVER_URL_EU,
    API_SERVER_URL_USA,
    API_SERVER_URL_CN,
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
