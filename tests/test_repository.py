"""Focused AUX Cloud tests."""

import pytest

from custom_components.aux_cloud.api import (
    AuxDeviceError,
)
from custom_components.aux_cloud.api.repository import AuxCloudRepository
from custom_components.aux_cloud.devices.profiles import (
    AC_MODE_SPECIAL,
    AUX_PROTOCOL_VERSION,
    AUX_QUERY_FAILURES,
    HP_HOT_WATER_TANK_TEMPERATURE,
    V3_HEAT_PUMP_QUERIES,
)

from .api_helpers import FakeInitialParamsControl as _FakeInitialParamsControl
from .api_helpers import FakeRepositorySession as _FakeRepositorySession
from .api_helpers import mock_device as _mock_device
from .api_helpers import mock_heat_pump as _mock_heat_pump


class TestAuxCloudAPI:
    """Tests for the AuxCloudAPI class."""

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

    @pytest.mark.parametrize(
        ("responses", "expected"),
        [
            (
                {
                    (): {"pwr": 1},
                    (AC_MODE_SPECIAL,): ValueError("special failed"),
                },
                {"pwr": 1},
            ),
            (
                {
                    (): ValueError("primary failed"),
                    (AC_MODE_SPECIAL,): {"mode": 4},
                },
                {"mode": 4},
            ),
        ],
    )
    async def test_repository_keeps_params_from_successful_queries(
        self, responses, expected
    ):
        """Test one failed bootstrap query does not discard usable state."""
        device = _mock_device()
        repository = AuxCloudRepository(
            _FakeRepositorySession(device), _FakeInitialParamsControl(responses)
        )

        devices = await repository.get_devices("family1")

        assert devices[0]["params"] == expected
        assert "last_updated" not in devices[0]

    async def test_repository_falls_back_to_v3_heat_pump_queries(self):
        """Test unsupported legacy HP GET resolves and caches the v3 dialect."""
        device = _mock_heat_pump(ver=2)
        control = _FakeInitialParamsControl(
            {
                (): AuxDeviceError(code=-49025),
                (HP_HOT_WATER_TANK_TEMPERATURE,): AuxDeviceError(code=-49025),
                ("ver",): {"ver": 4},
                ("ver", "key_states", "common_states"): {
                    "ver": 4,
                    "key_states": "000044",
                },
                ("ver", "hp_auto_wtemp", "water_tank_dif", "eco"): {"eco": 1},
                ("ver", "mute"): {"mute": 0},
            }
        )
        repository = AuxCloudRepository(
            _FakeRepositorySession(device),
            control,
        )

        devices = await repository.get_devices("family1")

        assert devices[0][AUX_PROTOCOL_VERSION] == 4
        assert devices[0]["params"][HP_HOT_WATER_TANK_TEMPERATURE] == 360
        assert devices[0][AUX_QUERY_FAILURES][0]["code"] == -49025
        assert control.queries == [
            [],
            [HP_HOT_WATER_TANK_TEMPERATURE],
            *[list(query) for query in V3_HEAT_PUMP_QUERIES],
        ]

        await repository.get_devices("family1")

        assert control.queries[-4:] == [list(query) for query in V3_HEAT_PUMP_QUERIES]

    async def test_repository_does_not_legacy_fallback_from_v3_metadata(self):
        """Test a failed v3 query cannot trigger a speculative legacy GET."""
        device = _mock_heat_pump(ver=3)
        control = _FakeInitialParamsControl(
            {
                ("ver",): AuxDeviceError(code=-49025),
                ("ver", "key_states", "common_states"): {"key_states": "000044"},
                ("ver", "hp_auto_wtemp", "water_tank_dif", "eco"): {"eco": 1},
                ("ver", "mute"): {"mute": 0},
            }
        )
        repository = AuxCloudRepository(_FakeRepositorySession(device), control)

        devices = await repository.get_devices("family1")

        assert control.queries == [list(query) for query in V3_HEAT_PUMP_QUERIES]
        assert [] not in control.queries
        assert devices[0][AUX_QUERY_FAILURES][0]["code"] == -49025

    async def test_repository_does_not_query_unknown_online_product(self):
        """Test an unaudited product receives no speculative state request."""
        device = _mock_device()
        device["productId"] = "unknown-product"
        control = _FakeInitialParamsControl({})
        repository = AuxCloudRepository(_FakeRepositorySession(device), control)

        devices = await repository.get_devices("family1")

        assert control.queries == []
        assert devices[0]["params"] == {}
