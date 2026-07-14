"""Behavior-level repository tests."""

from custom_components.aux_cloud.api import AuxDeviceError
from custom_components.aux_cloud.api.repository import AuxCloudRepository
from custom_components.aux_cloud.devices.profiles import (
    AC_MODE_SPECIAL,
    AUX_PROTOCOL_VERSION,
    AUX_QUERY_FAILURES,
    HP_HOT_WATER_TANK_TEMPERATURE,
    V3_HEAT_PUMP_QUERIES,
)

from .api_helpers import (
    FakeInitialParamsControl,
    FakeRepositorySession,
    mock_device,
    mock_heat_pump,
)


async def test_profiles_drive_bootstrap_while_offline_and_unknown_devices_are_safe():
    """Only audited, online devices receive their profile-owned query plan."""
    device = mock_device()
    control = FakeInitialParamsControl(
        {(): {"pwr": 1}, (AC_MODE_SPECIAL,): {"mode": 4}}
    )
    devices = await AuxCloudRepository(
        FakeRepositorySession(device), control
    ).get_devices("family1")
    assert control.queries == [[], [AC_MODE_SPECIAL]]
    assert devices[0]["params"] == {"pwr": 1, "mode": 4}

    for safe_device, online in ((mock_device(), False), (mock_device(), True)):
        if online:
            safe_device["productId"] = "unknown-product"
        safe_control = FakeInitialParamsControl({})
        devices = await AuxCloudRepository(
            FakeRepositorySession(safe_device, online=online), safe_control
        ).get_devices("family1")
        assert safe_control.queries == []
        assert devices[0]["params"] == {}


async def test_successful_query_batches_are_merged_independently():
    """A failed general or special query cannot discard the successful batch."""
    for responses, expected in (
        (
            {(): {"pwr": 1}, (AC_MODE_SPECIAL,): ValueError("special failed")},
            {"pwr": 1},
        ),
        (
            {(): ValueError("primary failed"), (AC_MODE_SPECIAL,): {"mode": 4}},
            {"mode": 4},
        ),
    ):
        device = mock_device()
        devices = await AuxCloudRepository(
            FakeRepositorySession(device), FakeInitialParamsControl(responses)
        ).get_devices("family1")
        assert devices[0]["params"] == expected


async def test_heat_pump_metadata_and_compatibility_fallback_select_v3_queries():
    """v3 metadata is authoritative; -49025 only upgrades stale legacy metadata."""
    stale = mock_heat_pump(ver=2)
    stale_control = FakeInitialParamsControl(
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
    repository = AuxCloudRepository(FakeRepositorySession(stale), stale_control)
    devices = await repository.get_devices("family1")
    assert devices[0][AUX_PROTOCOL_VERSION] == 4
    assert devices[0]["params"][HP_HOT_WATER_TANK_TEMPERATURE] == 360
    assert devices[0][AUX_QUERY_FAILURES][0]["code"] == -49025
    assert stale_control.queries == [
        [],
        [HP_HOT_WATER_TANK_TEMPERATURE],
        *[list(query) for query in V3_HEAT_PUMP_QUERIES],
    ]

    v3 = mock_heat_pump(ver=3)
    v3_control = FakeInitialParamsControl(
        {
            ("ver",): AuxDeviceError(code=-49025),
            ("ver", "key_states", "common_states"): {"key_states": "000044"},
            ("ver", "hp_auto_wtemp", "water_tank_dif", "eco"): {"eco": 1},
            ("ver", "mute"): {"mute": 0},
        }
    )
    devices = await AuxCloudRepository(
        FakeRepositorySession(v3), v3_control
    ).get_devices("family1")
    assert v3_control.queries == [list(query) for query in V3_HEAT_PUMP_QUERIES]
    assert [] not in v3_control.queries
    assert devices[0][AUX_QUERY_FAILURES][0]["code"] == -49025
