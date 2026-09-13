"""Behavior-level DNA inventory tests."""

from unittest.mock import AsyncMock, MagicMock

from custom_components.aux_cloud.api import AuxDeviceError
from custom_components.aux_cloud.device_metadata import (
    AUX_PROTOCOL_VERSION,
    AUX_QUERY_FAILURES,
)
from custom_components.aux_cloud.devices import (
    AC_MODE_SPECIAL,
    HP_HOT_WATER_TANK_TEMPERATURE,
    V3_HEAT_PUMP_QUERIES,
    DeviceType,
)
from custom_components.aux_cloud.dna.inventory import DeviceInventory

from .api_helpers import (
    FakeInitialParamsControl,
    FakeInventorySession,
    mock_device,
    mock_heat_pump,
)


async def test_empty_device_list_skips_state_and_bootstrap_queries() -> None:
    """Do not send querystate requests for empty personal or shared lists."""
    session = MagicMock(userid="user")
    session.make_request = AsyncMock(
        return_value={"status": 0, "data": {"endpoints": []}}
    )
    control = FakeInitialParamsControl({})

    devices = await DeviceInventory(session, control).get_devices("family1")

    assert devices == []
    session.make_request.assert_awaited_once()
    assert control.queries == []


async def test_profiles_drive_bootstrap_while_offline_and_unknown_devices_are_safe():
    """Only audited, online devices receive their profile-owned query plan."""
    device = mock_device()
    control = FakeInitialParamsControl(
        {(): {"pwr": 1}, (AC_MODE_SPECIAL,): {"mode": 4}}
    )
    devices = await DeviceInventory(FakeInventorySession(device), control).get_devices(
        "family1"
    )
    assert control.queries == [[], [AC_MODE_SPECIAL]]
    assert devices[0]["params"] == {"pwr": 1, "mode": 4}
    assert devices[0]["profile"].device_type is DeviceType.AIR_CONDITIONER

    for safe_device, online in ((mock_device(), False), (mock_device(), True)):
        if online:
            safe_device["productId"] = "unknown-product"
        safe_control = FakeInitialParamsControl({})
        devices = await DeviceInventory(
            FakeInventorySession(safe_device, online=online), safe_control
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
        devices = await DeviceInventory(
            FakeInventorySession(device), FakeInitialParamsControl(responses)
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
    inventory = DeviceInventory(FakeInventorySession(stale), stale_control)
    devices = await inventory.get_devices("family1")
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
    devices = await DeviceInventory(FakeInventorySession(v3), v3_control).get_devices(
        "family1"
    )
    assert v3_control.queries == [list(query) for query in V3_HEAT_PUMP_QUERIES]
    assert [] not in v3_control.queries
    assert devices[0][AUX_QUERY_FAILURES][0]["code"] == -49025
