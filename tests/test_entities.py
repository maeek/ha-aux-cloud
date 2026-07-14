"""Test AUX Cloud entity behavior and dynamic platform setup."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import ClimateEntityDescription, HVACMode
from homeassistant.components.climate.const import PRESET_ECO, PRESET_NONE, HVACAction
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.components.water_heater import (
    STATE_HEAT_PUMP,
    STATE_OFF,
    STATE_PERFORMANCE,
)
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.aux_cloud.climate as climate_platform
import custom_components.aux_cloud.number as number_platform
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
    AC_POWER_OFF,
    AC_SWING_HORIZONTAL,
    AC_SWING_VERTICAL,
    AC_TEMPERATURE_AMBIENT,
    AC_TEMPERATURE_DECIMAL,
    AC_TEMPERATURE_TARGET,
    AUX_MODE,
    HP_HEATER_POWER,
    HP_HEATER_TEMPERATURE_TARGET,
    HP_HOT_WATER_TANK_TEMPERATURE,
    HP_HOT_WATER_TEMPERATURE_TARGET,
    HP_MODE_COOLING,
    HP_MODE_HEATING,
    HP_QUIET_MODE,
    HP_WATER_FAST_HOTWATER,
    HP_WATER_POWER,
)
from custom_components.aux_cloud.number import POWER_LIMIT_DESCRIPTION, AuxNumberEntity
from custom_components.aux_cloud.select import SELECTS, AuxSelectEntity
from custom_components.aux_cloud.sensor import SENSORS, AuxCloudSensor
from custom_components.aux_cloud.switch import AuxSwitchEntity
from custom_components.aux_cloud.water_heater import (
    WATER_HEATER_DESCRIPTION,
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
    entry = MockConfigEntry(
        domain="aux_cloud",
        data={"email": "user@example.com", "password": "secret", "region": "eu"},
    )
    entry.add_to_hass(hass)
    coordinator = AuxCloudCoordinator(
        hass,
        api,
        config_entry=entry,
    )
    coordinator._state.reconcile(
        [device],
        complete=True,
        scan_revision=coordinator._state.revision,
    )
    coordinator._publish_devices()
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
    coordinator._state.reconcile(
        [first, second],
        complete=True,
        scan_revision=coordinator._state.revision,
    )
    coordinator._publish_devices()

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
        "params": {HP_HEATER_POWER: 1, AUX_MODE: HP_MODE_COOLING},
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
    description = SENSORS[AC_TEMPERATURE_AMBIENT]
    entity = AuxCloudSensor(
        coordinator,
        "00001234",
        description,
    )

    assert entity.native_value is None


def test_coordinator_failure_makes_entity_unavailable(hass):
    """Test a usable device snapshot is unavailable after coordinator failure."""
    coordinator = _coordinator(hass, _ac_device())
    entity = AuxACClimateEntity(
        coordinator,
        "00001234",
        ClimateEntityDescription(key="ac", translation_key="aux_ac"),
    )
    assert entity.available

    coordinator.last_update_success = False
    assert not entity.available


async def test_entity_command_propagates_failures(hass):
    """Test entity actions do not swallow Home Assistant errors."""
    coordinator = _coordinator(hass, _ac_device())
    coordinator.api.set_device_params.side_effect = HomeAssistantError("failed")
    switch = AuxSwitchEntity(
        coordinator,
        "00001234",
        SwitchEntityDescription(key=AC_POWER),
    )

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_off()


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
        next(
            description for description in SELECTS if description.key == HP_QUIET_MODE
        ),
    )

    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("unsupported")


async def test_select_exposes_option_and_sends_value(hass):
    """Test typed select metadata drives state and commands."""
    device = {
        "endpointId": "hp1",
        "friendlyName": "Heat Pump",
        "productId": HP_PRODUCT_ID,
        "state": 1,
        "params": {HP_QUIET_MODE: 0},
    }
    coordinator = _coordinator(hass, device)
    description = next(
        description for description in SELECTS if description.key == HP_QUIET_MODE
    )
    entity = AuxSelectEntity(
        coordinator,
        "hp1",
        description,
    )
    entity.async_write_ha_state = MagicMock()

    assert entity.current_option == "off"
    await entity.async_select_option("quiet_1")
    entity._handle_coordinator_update()
    assert entity.current_option == "quiet_1"


async def test_heat_pump_partial_state_and_commands(hass):
    """Test heat-pump omissions stay unknown and every supported command is bounded."""
    device = {
        "endpointId": "hp1",
        "friendlyName": "Heat Pump",
        "productId": HP_PRODUCT_ID,
        "state": 1,
        "params": {},
    }
    coordinator = _coordinator(hass, device)
    entity = AuxHeatPumpClimateEntity(
        coordinator,
        "hp1",
        ClimateEntityDescription(
            key="heat_pump_central_heating", translation_key="aux_heater"
        ),
    )
    params = entity._device["params"]

    assert entity.preset_mode is None
    assert entity.target_temperature is None
    assert entity.hvac_mode is None
    assert entity.hvac_action is None

    params[HP_HEATER_POWER] = 0
    assert entity.hvac_mode == HVACMode.OFF
    assert entity.hvac_action == HVACAction.OFF
    params.update({HP_HEATER_POWER: 1, AUX_MODE: HP_MODE_HEATING, "ecomode": 0})
    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.preset_mode == PRESET_NONE
    params["ecomode"] = 1
    assert entity.preset_mode == PRESET_ECO
    params[AUX_MODE] = 99
    assert entity.hvac_mode is None

    await entity.async_set_hvac_mode(HVACMode.HEAT)
    await entity.async_set_hvac_mode(HVACMode.COOL)
    await entity.async_set_hvac_mode(HVACMode.OFF)
    await entity.async_set_hvac_mode(HVACMode.AUTO)
    await entity.async_turn_on()
    await entity.async_turn_off()
    await entity.async_set_preset_mode(PRESET_ECO)
    await entity.async_set_preset_mode(PRESET_NONE)
    await entity.async_set_temperature()
    await entity.async_set_temperature(temperature="invalid")
    await entity.async_set_temperature(temperature=80)
    assert coordinator.api.set_device_params.await_args.args[1] == {
        HP_HEATER_TEMPERATURE_TARGET: 640
    }


async def test_ac_partial_state_and_commands(hass):
    """Test partial AC state stays unknown while supported controls remain usable."""
    device = _ac_device()
    coordinator = _coordinator(hass, device)
    entity = AuxACClimateEntity(
        coordinator,
        "00001234",
        ClimateEntityDescription(key="ac", translation_key="aux_ac"),
    )
    params = entity._device["params"]

    params.pop(AC_POWER)
    params.pop(AC_FAN_SPEED)
    params.pop(AC_SWING_HORIZONTAL)
    params.pop(AC_SWING_VERTICAL)
    assert entity.hvac_mode is None
    assert entity.hvac_action is None
    assert entity.fan_mode is None
    assert entity.swing_mode is None

    params[AC_POWER] = 0
    assert entity.hvac_mode == HVACMode.OFF
    params.update({AC_POWER: 1, AUX_MODE: 99, AC_FAN_SPEED: 99})
    assert entity.hvac_mode is None
    assert entity.fan_mode is None
    params.update({AC_SWING_HORIZONTAL: 1, AC_SWING_VERTICAL: 1})
    assert entity.swing_mode == "both"
    params[AC_SWING_HORIZONTAL] = 0
    assert entity.swing_mode == "vertical"

    await entity.async_set_temperature()
    await entity.async_set_temperature(temperature="invalid")
    await entity.async_set_hvac_mode(HVACMode.OFF)
    await entity.async_set_hvac_mode(HVACMode.HEAT)
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    await entity.async_set_fan_mode(None)
    await entity.async_set_fan_mode("unsupported")
    await entity.async_set_fan_mode("high")
    await entity.async_set_swing_mode("both")
    await entity.async_turn_on()
    await entity.async_turn_off()
    assert coordinator.api.set_device_params.await_args.args[1] == AC_POWER_OFF


def test_partial_scalar_entities_are_unknown(hass):
    """Test omitted scalar keys do not fabricate off, zero, or a select option."""
    device = _ac_device("device1")
    coordinator = _coordinator(hass, device)
    switch = AuxSwitchEntity(
        coordinator, "device1", SwitchEntityDescription(key=AC_POWER)
    )
    number = AuxNumberEntity(coordinator, "device1", POWER_LIMIT_DESCRIPTION)
    switch._device["params"].pop(AC_POWER)
    assert switch.is_on is None
    assert number.native_value is None

    hp_device = {
        "endpointId": "hp1",
        "productId": HP_PRODUCT_ID,
        "state": 1,
        "params": {},
    }
    hp_coordinator = _coordinator(hass, hp_device)
    select = AuxSelectEntity(
        hp_coordinator,
        "hp1",
        next(
            description for description in SELECTS if description.key == HP_QUIET_MODE
        ),
    )
    water = AuxWaterHeaterEntity(hp_coordinator, "hp1", WATER_HEATER_DESCRIPTION)
    assert select.current_option is None
    assert water.current_temperature is None
    assert water.target_temperature is None
    assert water.current_operation is None
    water._device["params"][HP_WATER_POWER] = 1
    assert water.current_operation is None
    water._device["params"].update({HP_WATER_POWER: 2, HP_WATER_FAST_HOTWATER: 0})
    assert water.current_operation is None


def test_icons_are_translation_backed():
    """Test static and state-dependent entity icons are declared in icons.json."""
    icons = json.loads(
        (
            Path(__file__).parents[1] / "custom_components" / "aux_cloud" / "icons.json"
        ).read_text(encoding="utf-8")
    )["entity"]
    assert icons["climate"]["aux_ac"]["default"] == "mdi:air-conditioner"
    assert icons["select"]["aux_select_qtmode"]["state"]["off"] == "mdi:volume-high"


async def test_number_entity_and_platform_setup(hass):
    """Test the power limit number is discoverable, readable, and writable."""
    device = _ac_device("device1")
    device["params"][AC_POWER_LIMIT] = 40
    coordinator = _coordinator(hass, device)
    entity = AuxNumberEntity(coordinator, "device1", POWER_LIMIT_DESCRIPTION)
    entity.async_write_ha_state = MagicMock()

    assert entity.native_value == 40
    await entity.async_set_native_value(55.9)
    entity._handle_coordinator_update()
    assert entity.native_value == 55

    entry = SimpleNamespace(runtime_data=coordinator, async_on_unload=MagicMock())
    add_entities = MagicMock()
    await number_platform.async_setup_entry(hass, entry, add_entities)
    assert len(add_entities.call_args.args[0]) == 1
    entry.async_on_unload.call_args.args[0]()


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
        WATER_HEATER_DESCRIPTION,
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
        runtime_data=coordinator,
        async_on_unload=MagicMock(),
    )
    add_entities = MagicMock()

    await sensor_platform.async_setup_entry(hass, entry, add_entities)
    coordinator._state.reconcile(
        [_ac_device("device1"), _ac_device("device2")],
        complete=True,
        scan_revision=coordinator._state.revision,
    )
    coordinator._publish_devices()

    assert add_entities.call_count == 2
    first_unique_ids = {
        entity.unique_id for entity in add_entities.call_args_list[0].args[0]
    }
    second_unique_ids = {
        entity.unique_id for entity in add_entities.call_args_list[1].args[0]
    }
    assert first_unique_ids.isdisjoint(second_unique_ids)
    entry.async_on_unload.call_args.args[0]()


async def test_climate_and_switch_platform_factories(hass):
    """Test platform factories use published runtime data and static descriptions."""
    coordinator = _coordinator(hass, _ac_device("device1"))
    entry = SimpleNamespace(runtime_data=coordinator, async_on_unload=MagicMock())
    climates = MagicMock()
    switches = MagicMock()

    await climate_platform.async_setup_entry(hass, entry, climates)
    climate_unload = entry.async_on_unload.call_args.args[0]
    await switch_platform.async_setup_entry(hass, entry, switches)
    switch_unload = entry.async_on_unload.call_args.args[0]

    assert isinstance(climates.call_args.args[0][0], AuxACClimateEntity)
    assert all(
        isinstance(entity, AuxSwitchEntity) for entity in switches.call_args.args[0]
    )
    power_switch = next(
        entity
        for entity in switches.call_args.args[0]
        if entity.entity_description.key == AC_POWER
    )
    power_switch.async_write_ha_state = MagicMock()
    assert power_switch.is_on
    await power_switch.async_turn_off()
    power_switch._handle_coordinator_update()
    assert not power_switch.is_on
    await power_switch.async_turn_on()

    climate_unload()
    switch_unload()

    heat_pump = {
        "endpointId": "hp1",
        "friendlyName": "Heat Pump",
        "productId": HP_PRODUCT_ID,
        "state": 1,
        "params": {HP_WATER_POWER: 1},
    }
    hp_coordinator = _coordinator(hass, heat_pump)
    hp_entry = SimpleNamespace(runtime_data=hp_coordinator, async_on_unload=MagicMock())
    water_heaters = MagicMock()
    await water_heater_platform.async_setup_entry(hass, hp_entry, water_heaters)
    assert isinstance(water_heaters.call_args.args[0][0], AuxWaterHeaterEntity)
    hp_entry.async_on_unload.call_args.args[0]()
