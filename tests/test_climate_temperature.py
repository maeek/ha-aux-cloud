"""Tests for AUX AC target-temperature encoding and debounce behavior.

These deliberately avoid the pytest_homeassistant_custom_component `hass`
fixture (which needs a real event loop) so they stay fast and lightweight -
they only need a fake hass/coordinator that quacks like the real thing.
"""

import asyncio
from unittest.mock import MagicMock, AsyncMock

import pytest
from homeassistant.components.climate import ClimateEntityDescription
from homeassistant.const import UnitOfTemperature

from custom_components.aux_cloud.api.const import (
    AC_TEMPERATURE_AMBIENT,
    AC_TEMPERATURE_CONVERT,
    AC_TEMPERATURE_TARGET,
    AC_TEMPERATURE_UNIT,
)
from custom_components.aux_cloud.climate import AuxACClimateEntity
from custom_components.aux_cloud.const import SET_TEMPERATURE_DEBOUNCE_SECONDS
from custom_components.aux_cloud.util import DeviceStateHelper


class FakeHass:
    """Minimal stand-in for HomeAssistant that just runs background tasks."""

    def async_create_task(self, coro):
        return asyncio.ensure_future(coro)


class FakeCoordinator:
    """Minimal stand-in for AuxCloudCoordinator."""

    def __init__(self, initial_params: dict):
        self.api = MagicMock()
        self.api.set_device_params = AsyncMock(return_value={})
        self.async_request_refresh = AsyncMock()
        self._device = {
            "endpointId": "device1",
            "friendlyName": "Living Room Mini split",
            "productId": "000000000000000000000000c0620000",
            "params": initial_params,
        }
        self._helper = None

    def get_device_by_endpoint_id(self, device_id):
        return self._device

    def get_state_helper(self, device_id, initial_params):
        if self._helper is None:
            self._helper = DeviceStateHelper(initial_params, max_failed_polls=5)
        return self._helper


def make_ac_entity(
    initial_temp_tenths=200,
    tempunit=None,
    temp_convert=None,
    ambient_temp_tenths=None,
):
    initial_params = {AC_TEMPERATURE_TARGET: initial_temp_tenths}
    if tempunit is not None:
        initial_params[AC_TEMPERATURE_UNIT] = tempunit
    if temp_convert is not None:
        initial_params[AC_TEMPERATURE_CONVERT] = temp_convert
    if ambient_temp_tenths is not None:
        initial_params[AC_TEMPERATURE_AMBIENT] = ambient_temp_tenths

    coordinator = FakeCoordinator(initial_params)
    entity = AuxACClimateEntity(
        coordinator, "device1", ClimateEntityDescription(key="ac", name="AC")
    )
    entity.hass = FakeHass()
    entity.async_write_ha_state = MagicMock()
    return entity, coordinator


class TestCelsiusEncoding:
    """Celsius-mode devices accept whole-Celsius-degree setpoints."""

    @pytest.mark.parametrize(
        "celsius_input,expected_tenths",
        [
            (20.0, 200),
            (22.777777777777779, 230),
            (23.333333333333332, 230),
            (23.888888888888889, 240),
            (25.0, 250),
        ],
    )
    async def test_set_temperature_snaps_to_whole_degree(
        self, celsius_input, expected_tenths
    ):
        entity, coordinator = make_ac_entity()

        await entity.async_set_temperature(temperature=celsius_input)
        # Let the debounced send fire.
        await asyncio.sleep(SET_TEMPERATURE_DEBOUNCE_SECONDS + 0.2)

        coordinator.api.set_device_params.assert_called_once()
        sent_params = coordinator.api.set_device_params.call_args[0][1]
        assert sent_params == {AC_TEMPERATURE_TARGET: expected_tenths}
        assert sent_params[AC_TEMPERATURE_TARGET] % 10 == 0


class TestFahrenheitEncoding:
    """Fahrenheit-mode devices use temp and ac_tempconvert together."""

    def test_target_temperature_decodes_to_exact_displayed_fahrenheit(self):
        entity, _ = make_ac_entity(
            initial_temp_tenths=240,
            tempunit=2,
            temp_convert=2,
            ambient_temp_tenths=236,
        )

        assert entity.target_temperature == 76
        assert entity.current_temperature == pytest.approx(74.48)
        assert entity.temperature_unit == UnitOfTemperature.FAHRENHEIT
        assert entity.min_temp == 60
        assert entity.max_temp == 90
        assert entity.target_temperature_step == 1

    async def test_set_temperature_sends_ac_freedom_wire_format(self):
        entity, coordinator = make_ac_entity(
            initial_temp_tenths=240,
            tempunit=2,
            temp_convert=2,
        )

        await entity.async_set_temperature(temperature=76)
        await asyncio.sleep(SET_TEMPERATURE_DEBOUNCE_SECONDS + 0.2)

        sent_params = coordinator.api.set_device_params.call_args[0][1]
        assert sent_params == {
            AC_TEMPERATURE_UNIT: 2,
            AC_TEMPERATURE_TARGET: 240,
            AC_TEMPERATURE_CONVERT: 4,
        }


class TestSetTemperatureDebounce:
    """Rapid successive calls should collapse into a single network send."""

    async def test_rapid_calls_send_only_final_value(self):
        entity, coordinator = make_ac_entity()

        for celsius in [23.3, 25.2, 24.7, 25.0, 23.3]:
            await entity.async_set_temperature(temperature=celsius)
            await asyncio.sleep(0.05)  # faster than the debounce window

        assert coordinator.api.set_device_params.call_count == 0

        await asyncio.sleep(SET_TEMPERATURE_DEBOUNCE_SECONDS + 0.3)

        assert coordinator.api.set_device_params.call_count == 1
        sent_params = coordinator.api.set_device_params.call_args[0][1]
        # Last requested value was 23.3C -> rounds to 23C -> 230
        assert sent_params == {AC_TEMPERATURE_TARGET: 230}

    async def test_single_call_still_sends_after_debounce_window(self):
        entity, coordinator = make_ac_entity()

        await entity.async_set_temperature(temperature=25.0)
        assert coordinator.api.set_device_params.call_count == 0

        await asyncio.sleep(SET_TEMPERATURE_DEBOUNCE_SECONDS + 0.3)

        assert coordinator.api.set_device_params.call_count == 1
