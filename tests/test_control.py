"""Focused AUX Cloud tests."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.aux_cloud.api import AuxCloudAPI

from .api_helpers import mock_device as _mock_device


@pytest.fixture
def aux_api():
    """Return a new AuxCloudAPI instance."""
    return AuxCloudAPI(region="eu", session=MagicMock(closed=False))


class TestAuxCloudAPI:
    """Tests for the AuxCloudAPI class."""

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
        aux_api._websocket = fake_ws
        aux_api._session.loginsession = "session"
        aux_api._session.userid = "user"

        result = await aux_api.set_device_params(device, {"pwr": 1})

        assert result == {"pwr": 1}
        assert fake_ws.sent_data is not None

    async def test_set_device_params_falls_back_to_http(self, aux_api):
        """Test HTTP fallback when websocket command fails."""
        device = _mock_device()

        class FailingWebSocket:
            connected = True

            async def async_send_opencontrol(self, data, timeout=10):
                raise TimeoutError

        aux_api._websocket = FailingWebSocket()
        aux_api._control._act_http = AsyncMock(return_value={"pwr": 1})

        result = await aux_api.set_device_params(device, {"pwr": 1})

        assert result == {"pwr": 1}
        aux_api._control._act_http.assert_awaited_once()
