"""Test AUX Cloud entity behavior and dynamic platform setup."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import ClimateEntityDescription, HVACMode
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.components.water_heater import (
    STATE_HEAT_PUMP,
    STATE_OFF,
    STATE_PERFORMANCE,
)
from homeassistant.exceptions import HomeAssistantError

import custom_components.aux_cloud.climate as climate_platform
import custom_components.aux_cloud.number as number_platform
import custom_components.aux_cloud.select as select_platform
import custom_components.aux_cloud.sensor as sensor_platform
import custom_components.aux_cloud.switch as switch_platform
import custom_components.aux_cloud.water_heater as water_heater_platform
from custom_components.aux_cloud.climate import (
    AuxACClimateEntity,
    AuxHeatPumpClimateEntity,
)
from custom_components.aux_cloud.coordinator import AuxCloudCoordinator
from custom_components.aux_cloud.devices.profiles import (
    AC_FAN_SPEED,
    AC_POWER,
    AC_POWER_LIMIT,
    AC_SWING_HORIZONTAL,
    AC_SWING_VERTICAL,
    AC_TEMPERATURE_AMBIENT,
    AC_TEMPERATURE_DECIMAL,
    AC_TEMPERATURE_TARGET,
    AUX_MODE,
    HP_HEATER_POWER,
    HP_HOT_WATER_TANK_TEMPERATURE,
    HP_HOT_WATER_TEMPERATURE_TARGET,
    HP_MODE_COOLING,
    HP_QUIET_MODE,
    HP_WATER_FAST_HOTWATER,
    HP_WATER_POWER,
)
from custom_components.aux_cloud.number import AuxNumberEntity
from custom_components.aux_cloud.select import AuxSelectEntity
from custom_components.aux_cloud.sensor import SENSORS, AuxCloudSensor
from custom_components.aux_cloud.switch import AuxSwitchEntity
from custom_components.aux_cloud.water_heater import (
    WATER_HEATER_ENTITIES,
    AuxWaterHeaterEntity,
)

pytest_plugins = "pytest_homeassistant_custom_component"

AC_PRODUCT_ID = "000000000000000000000000c0620000"
HP_PRODUCT_ID = "000000000000000000000000c3aa0000"


def _coordinator(hass, device):
    api = MagicMock()
    api.normalize_device_params = MagicMock()
    api.set_device_params = AsyncMock(side_effect=lambda _device, params: params)
    api.close_websocket = AsyncMock()
    coordinator = AuxCloudCoordinator(
        hass,
        api,
        email="user@example.com",
        password="secret",
    )
    coordinator.devices = [device]
    coordinator.async_set_updated_data({"devices": coordinator.devices})
    return coordinator


def _ac_device(endpoint_id="00001234"):
    return {
        "endpointId": endpoint_id,
        "friendlyName": "Bedroom",
        "productId": AC_PRODUCT_ID,
        "state": 1,
        "params": {
            AC_POWER: 1,
            AUX_MODE: 0,
            AC_FAN_SPEED: 0,
            AC_SWING_HORIZONTAL: 1,
            AC_SWING_VERTICAL: 0,
            AC_TEMPERATURE_AMBIENT: 215,
            AC_TEMPERATURE_TARGET: 230,
        },
    }


def test_ac_climate_reads_state_and_preserves_unique_id(hass):
    """Test climate state mapping and the released unique-ID formula."""
    coordinator = _coordinator(hass, _ac_device())
    entity = AuxACClimateEntity(
        coordinator,
        "00001234",
        ClimateEntityDescription(key="ac", translation_key="aux_ac"),
    )

    assert entity.unique_id == "aux_cloud_1234_ac"
    assert entity.current_temperature == 21.5
    assert entity.target_temperature == 23
    assert entity.hvac_mode == HVACMode.COOL
    assert entity.swing_mode == "horizontal"


@pytest.mark.parametrize(
    ("suffix", "has_auto", "fan_modes", "swing_modes"),
    [
        (
            "c5510000",
            False,
            [
                "auto",
                "low",
                "medium_low",
                "medium",
                "medium_high",
                "high",
                "turbo",
                "silent",
            ],
            ["off", "vertical", "horizontal", "both"],
        ),
        (
            "56ac0000",
            True,
            ["low", "medium", "high"],
            ["off", "vertical"],
        ),
    ],
)
def test_ac_climate_uses_product_capabilities(
    hass, suffix, has_auto, fan_modes, swing_modes
):
    """Test climate options omit commands that an APK product cannot accept."""
    device = _ac_device()
    device["productId"] = f"{'0' * 24}{suffix}"
    coordinator = _coordinator(hass, device)
    entity = AuxACClimateEntity(
        coordinator,
        "00001234",
        ClimateEntityDescription(key="ac", translation_key="aux_ac"),
    )

    assert (HVACMode.AUTO in entity.hvac_modes) is has_auto
    assert entity.fan_modes == fan_modes
    assert entity.swing_modes == swing_modes
    assert entity.unique_id == "aux_cloud_1234_ac"


def test_new_endpoint_collision_uses_deterministic_v2_unique_id(hass):
    """Test a new colliding endpoint cannot break the released legacy entity."""
    first = _ac_device("00001234")
    second = _ac_device("1234")
    coordinator = _coordinator(hass, first)
    coordinator.devices.append(second)
    coordinator.async_set_updated_data({"devices": coordinator.devices})

    first_entity = AuxSwitchEntity(
        coordinator,
        "00001234",
        SwitchEntityDescription(key=AC_POWER),
    )
    second_entity = AuxSwitchEntity(
        coordinator,
        "1234",
        SwitchEntityDescription(key=AC_POWER),
    )

    assert first_entity.unique_id == "aux_cloud_1234_pwr"
    assert second_entity.unique_id.startswith("aux_cloud_1234_pwr_v2_")


async def test_ac_climate_command_updates_coordinator(hass):
    """Test entity commands use the coordinator transaction path."""
    coordinator = _coordinator(hass, _ac_device())
    entity = AuxACClimateEntity(
        coordinator,
        "00001234",
        ClimateEntityDescription(key="ac", translation_key="aux_ac"),
    )

    await entity.async_set_temperature(temperature=24.5)

    assert (
        coordinator.get_device_by_endpoint_id("00001234")["params"][
            AC_TEMPERATURE_TARGET
        ]
        == 245
    )


async def test_half_degree_product_uses_decimal_flag_without_changing_unique_id(hass):
    """Test the APK-specific wire quirk stays behind the existing entity identity."""
    device = _ac_device()
    device["productId"] = f"{'0' * 24}1f620000"
    coordinator = _coordinator(hass, device)
    entity = AuxACClimateEntity(
        coordinator,
        "00001234",
        ClimateEntityDescription(key="ac", translation_key="aux_ac"),
    )

    await entity.async_set_temperature(temperature=24.5)

    assert entity.unique_id == "aux_cloud_1234_ac"
    assert coordinator.api.set_device_params.await_args.args[1] == {
        AC_TEMPERATURE_TARGET: 240,
        AC_TEMPERATURE_DECIMAL: 1,
    }


def test_heat_pump_reports_cooling_mode(hass):
    """Test heat-pump HVAC state no longer always reports heating."""
    device = {
        "endpointId": "hp1",
        "friendlyName": "Heat Pump",
        "productId": HP_PRODUCT_ID,
        "state": 1,
        "params": {HP_HEATER_POWER: 1, AUX_MODE: HP_MODE_COOLING[AUX_MODE]},
    }
    coordinator = _coordinator(hass, device)
    entity = AuxHeatPumpClimateEntity(
        coordinator,
        "hp1",
        ClimateEntityDescription(
            key="heat_pump_central_heating", translation_key="aux_heater"
        ),
    )

    assert entity.hvac_mode == HVACMode.COOL


def test_missing_sensor_value_is_unknown(hass):
    """Test omitted cloud values do not become false zero measurements."""
    device = _ac_device()
    device["params"].pop(AC_TEMPERATURE_AMBIENT)
    coordinator = _coordinator(hass, device)
    definition = SENSORS[AC_TEMPERATURE_AMBIENT]
    entity = AuxCloudSensor(
        coordinator,
        "00001234",
        definition["description"],
        definition["get_fn"],
    )

    assert entity.native_value is None


async def test_switch_and_number_commands_propagate_failures(hass):
    """Test entity actions raise Home Assistant errors instead of swallowing them."""
    coordinator = _coordinator(hass, _ac_device())
    coordinator.api.set_device_params.side_effect = HomeAssistantError("failed")
    switch = AuxSwitchEntity(
        coordinator,
        "00001234",
        SwitchEntityDescription(key=AC_POWER),
    )
    number = AuxNumberEntity(
        coordinator,
        "00001234",
        NumberEntityDescription(key=AC_POWER_LIMIT),
    )

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_off()
    with pytest.raises(HomeAssistantError):
        await number.async_set_native_value(50)


async def test_select_rejects_unknown_option(hass):
    """Test invalid select actions fail explicitly and translatably."""
    device = {
        "endpointId": "hp1",
        "friendlyName": "Heat Pump",
        "productId": HP_PRODUCT_ID,
        "state": 1,
        "params": {HP_QUIET_MODE: 0},
    }
    coordinator = _coordinator(hass, device)
    entity = AuxSelectEntity(
        coordinator,
        "hp1",
        SelectEntityDescription(key=HP_QUIET_MODE),
        {"off": {"value": 0, "icon": "mdi:volume-high"}},
    )

    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("unsupported")


async def test_water_heater_state_and_commands(hass):
    """Test water-heater temperatures, operations, and invalid actions."""
    device = {
        "endpointId": "hp1",
        "friendlyName": "Heat Pump",
        "productId": HP_PRODUCT_ID,
        "state": 1,
        "params": {
            HP_HOT_WATER_TANK_TEMPERATURE: 45,
            HP_HOT_WATER_TEMPERATURE_TARGET: 500,
            HP_WATER_POWER: 1,
            HP_WATER_FAST_HOTWATER: 0,
        },
    }
    coordinator = _coordinator(hass, device)
    entity = AuxWaterHeaterEntity(
        coordinator,
        "hp1",
        WATER_HEATER_ENTITIES["water_heater"]["description"],
    )
    entity.async_write_ha_state = MagicMock()

    assert entity.current_temperature == 45
    assert entity.target_temperature == 50
    assert entity.current_operation == STATE_HEAT_PUMP
    assert entity.operation_list == [STATE_OFF, STATE_HEAT_PUMP, STATE_PERFORMANCE]

    await entity.async_set_operation_mode(STATE_PERFORMANCE)
    entity._handle_coordinator_update()
    assert entity.current_operation == STATE_PERFORMANCE
    await entity.async_set_operation_mode(STATE_OFF)
    entity._handle_coordinator_update()
    assert entity.current_operation == STATE_OFF
    await entity.async_set_temperature(temperature=52)
    entity._handle_coordinator_update()
    assert entity.target_temperature == 52

    with pytest.raises(HomeAssistantError):
        await entity.async_set_operation_mode("invalid")


async def test_sensor_platform_adds_devices_discovered_later(hass):
    """Test a topology scan can add entities without reloading the entry."""
    coordinator = _coordinator(hass, _ac_device("device1"))
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(coordinator=coordinator),
        async_on_unload=MagicMock(),
    )
    add_entities = MagicMock()

    await sensor_platform.async_setup_entry(hass, entry, add_entities)
    listener = next(iter(coordinator._device_listeners))
    listener([_ac_device("device2")])

    assert add_entities.call_count == 2
    first_unique_ids = {
        entity.unique_id for entity in add_entities.call_args_list[0].args[0]
    }
    second_unique_ids = {
        entity.unique_id for entity in add_entities.call_args_list[1].args[0]
    }
    assert first_unique_ids.isdisjoint(second_unique_ids)


@pytest.mark.parametrize(
    ("platform", "device"),
    [
        (climate_platform, _ac_device()),
        (number_platform, _ac_device()),
        (switch_platform, _ac_device()),
        (
            climate_platform,
            {
                "endpointId": "hp1",
                "friendlyName": "Heat Pump",
                "productId": HP_PRODUCT_ID,
                "state": 1,
                "params": {HP_HEATER_POWER: 1},
            },
        ),
        (
            select_platform,
            {
                "endpointId": "hp1",
                "friendlyName": "Heat Pump",
                "productId": HP_PRODUCT_ID,
                "state": 1,
                "params": {HP_QUIET_MODE: 0},
            },
        ),
        (
            water_heater_platform,
            {
                "endpointId": "hp1",
                "friendlyName": "Heat Pump",
                "productId": HP_PRODUCT_ID,
                "state": 1,
                "params": {HP_WATER_POWER: 1},
            },
        ),
    ],
)
async def test_platform_setup_adds_supported_entities(hass, platform, device):
    """Test every platform uses runtime data and registers dynamic discovery."""
    coordinator = _coordinator(hass, device)
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(coordinator=coordinator),
        async_on_unload=MagicMock(),
    )
    add_entities = MagicMock()

    await platform.async_setup_entry(hass, entry, add_entities)

    add_entities.assert_called_once()
    assert add_entities.call_args.args[0]
    entry.async_on_unload.assert_called_once()
