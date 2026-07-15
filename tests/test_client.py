"""Focused DNA client tests."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import custom_components.aux_cloud.dna.client as client_module
from custom_components.aux_cloud.api.errors import AuxAuthError, AuxServerError
from custom_components.aux_cloud.dna import DnaClient

from .api_helpers import mock_device as _mock_device


@pytest.fixture
def aux_api():
    """Return a new DNA client instance."""
    return DnaClient(region="eu", session=MagicMock(closed=False))


class TestDnaClient:
    """Tests for the DNA client."""

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

    async def test_scan_devices_keeps_partial_results_and_deduplicates(self, aux_api):
        """One failed family query does not hide a usable account inventory."""
        device = _mock_device()
        aux_api._inventory.get_families = AsyncMock(
            return_value=[{"familyid": "family1"}]
        )
        aux_api._inventory.get_devices = AsyncMock(
            side_effect=[[device, dict(device)], AuxServerError("shared failed")]
        )

        snapshot = await aux_api.scan_devices()

        assert snapshot.devices == (device,)
        assert snapshot.complete is False

        aux_api._inventory.get_devices.side_effect = [
            AuxServerError("personal failed"),
            AuxAuthError("session rejected"),
        ]
        with pytest.raises(AuxAuthError):
            await aux_api.scan_devices()

    async def test_set_device_params_falls_back_to_http(self, aux_api):
        """Test HTTP fallback when websocket command fails."""
        device = _mock_device()

        class FailingWebSocket:
            connected = True

            async def async_send_opencontrol(self, data, timeout=10):
                raise TimeoutError

        aux_api._websocket = FailingWebSocket()
        aux_api._act_http = AsyncMock(return_value={"pwr": 1})

        result = await aux_api.set_device_params(device, {"pwr": 1})

        assert result == {"pwr": 1}
        aux_api._act_http.assert_awaited_once()

    async def test_realtime_retries_and_reports_health(self, aux_api, monkeypatch):
        """The API facade owns relay retry policy and health notifications."""
        monkeypatch.setattr(client_module, "_RETRY_INITIAL_DELAY", 0)
        monkeypatch.setattr(client_module.asyncio, "sleep", AsyncMock())
        ready = asyncio.Event()
        attempts = 0

        async def run_once(_devices, _listener, on_ready):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise AuxServerError("relay unavailable")
            on_ready()
            ready.set()
            await asyncio.Event().wait()

        aux_api._run_websocket_once = AsyncMock(side_effect=run_once)
        health = []
        task = asyncio.create_task(
            aux_api.run_realtime(connection_listener=health.append)
        )
        await asyncio.wait_for(ready.wait(), timeout=1)

        assert attempts == 2
        assert health == [False, True]

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
