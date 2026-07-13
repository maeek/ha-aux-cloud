"""Focused AUX Cloud tests."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.aux_cloud.api import (
    AuxCloudAPI,
    AuxDeviceError,
    AuxSessionExpired,
)
from custom_components.aux_cloud.devices.profiles import (
    AC_POWER_LIMIT,
)

from .api_helpers import mock_device as _mock_device


@pytest.fixture
def aux_api():
    """Return a new AuxCloudAPI instance."""
    return AuxCloudAPI(region="eu", session=MagicMock(closed=False))


class TestAuxCloudAPI:
    """Tests for the AuxCloudAPI class."""

    async def test_unsupported_product_command_is_rejected_before_transport(
        self, aux_api
    ):
        """Test product profiles prevent known-unsafe parameters from being sent."""
        device = _mock_device()
        device["productId"] = f"{'0' * 24}c9100100"
        aux_api._control._act_http = AsyncMock()

        with pytest.raises(AuxDeviceError):
            await aux_api.set_device_params(device, {AC_POWER_LIMIT: 50})

        aux_api._control._act_http.assert_not_awaited()

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

    async def test_unknown_relay_ack_falls_back_to_http(self, aux_api):
        """Test undocumented relay failures follow the documented HTTP fallback."""
        websocket = MagicMock(connected=True)
        websocket.async_send_opencontrol = AsyncMock(
            return_value={"msgtype": "transit.opencontrolk", "status": 7}
        )
        aux_api._websocket = websocket
        aux_api._control._act_http = AsyncMock(return_value={"pwr": 1})

        assert await aux_api.set_device_params(_mock_device(), {"pwr": 1}) == {"pwr": 1}
        aux_api._control._act_http.assert_awaited_once()

    async def test_command_session_expiry_recovers_then_uses_http(self, aux_api):
        """Test a stale relay session is replaced before the HTTP command retry."""
        aux_api._session.loginsession = "expired"
        aux_api._control.set_device_params = AsyncMock(side_effect=AuxSessionExpired())
        aux_api._control.set_device_params_http = AsyncMock(return_value={"pwr": 1})
        aux_api._session.recover_session = AsyncMock(return_value=True)
        aux_api.close_websocket = AsyncMock()

        result = await aux_api.set_device_params(_mock_device(), {"pwr": 1})

        assert result == {"pwr": 1}
        aux_api.close_websocket.assert_awaited_once()
        aux_api._session.recover_session.assert_awaited_once_with(
            expired_session="expired"
        )

    async def test_http_control_boundary_parses_event(self, aux_api):
        """Test the collapsed control boundary builds and parses an HTTP request."""
        aux_api._session.make_request = AsyncMock(
            return_value={
                "event": {
                    "header": {"name": "Response"},
                    "payload": {"status": 0, "data": {"pwr": 1}},
                }
            }
        )

        result = await aux_api._control.get_device_params(_mock_device(), ["pwr"])

        assert result == {"pwr": 1}
        assert aux_api._session.make_request.await_args.args[0].endswith("sdkcontrol")
