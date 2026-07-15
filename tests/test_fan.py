"""Tests for AUX air conditioner fan support."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.fan import FanEntityDescription

from custom_components.aux_cloud.api.const import ACFanSpeed
from custom_components.aux_cloud.const import DEFAULT_AC_FAN_MODES
from custom_components.aux_cloud.fan import AuxACFanEntity
from custom_components.aux_cloud.util import DeviceStateHelper, get_ac_fan_modes


def _device_cookie(fan_speeds: list[int]) -> str:
    profile = {"suids": [{"intfs": {"ac_mark": [{"idx": 1, "in": fan_speeds}]}}]}
    cookie = {"profile": json.dumps(profile)}
    return base64.b64encode(json.dumps(cookie).encode()).decode()


def test_get_ac_fan_modes_uses_profile_and_safe_fallback():
    """Use advertised modes without changing legacy devices."""
    assert get_ac_fan_modes({"cookie": _device_cookie([0, 1, 2, 3])}) == [
        "auto",
        "low",
        "medium",
        "high",
    ]
    assert get_ac_fan_modes({"cookie": _device_cookie(list(range(8)))}) == [
        "auto",
        "silent",
        "low",
        "medium-low",
        "medium",
        "medium-high",
        "high",
        "turbo",
    ]
    assert get_ac_fan_modes({"cookie": "invalid"}) == DEFAULT_AC_FAN_MODES


async def test_fan_maps_all_manual_modes_to_percentage():
    """Expose five legacy manual modes as five percentage steps."""
    device = {
        "endpointId": "device1",
        "friendlyName": "AC Unit 1",
        "productId": "000000000000000000000000c0620000",
        "params": {"pwr": 1, "ac_mark": ACFanSpeed.MUTE},
    }
    coordinator = MagicMock()
    coordinator.get_device_by_endpoint_id.return_value = device
    coordinator.get_state_helper.return_value = DeviceStateHelper(device["params"], 5)
    coordinator.api.set_device_params = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    entity = AuxACFanEntity(
        coordinator,
        "device1",
        FanEntityDescription(key="fan", name="Fan"),
        list(DEFAULT_AC_FAN_MODES),
    )
    entity.async_write_ha_state = MagicMock()

    assert entity.percentage_step == 20
    assert entity.percentage == 20
    await entity.async_set_percentage(40)

    coordinator.api.set_device_params.assert_awaited_once_with(
        device, {"pwr": 1, "ac_mark": ACFanSpeed.LOW}
    )
    assert entity.percentage == 40

    await entity.async_set_preset_mode("auto")
    coordinator.api.set_device_params.assert_awaited_with(
        device, {"pwr": 1, "ac_mark": ACFanSpeed.AUTO}
    )
    assert entity.preset_mode == "auto"
    assert entity.percentage is None

    await entity.async_set_percentage(0)
    coordinator.api.set_device_params.assert_awaited_with(device, {"pwr": 0})
    assert entity.is_on is False
    assert entity.percentage == 0
