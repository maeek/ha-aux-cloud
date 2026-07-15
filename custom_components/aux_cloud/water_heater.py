"""Water-heater platform for AUX Cloud."""

from typing import Any

from homeassistant.components.water_heater import (
    STATE_HEAT_PUMP,
    STATE_PERFORMANCE,
    WaterHeaterEntity,
    WaterHeaterEntityDescription,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api.models import AuxDevice
from .const import DOMAIN
from .coordinator import AuxCloudConfigEntry, AuxCloudCoordinator
from .devices import (
    HP_HOT_WATER_TANK_TEMPERATURE,
    HP_HOT_WATER_TEMPERATURE_TARGET,
    HP_WATER_FAST_HOTWATER,
    HP_WATER_FAST_HOTWATER_OFF,
    HP_WATER_FAST_HOTWATER_ON,
    HP_WATER_POWER,
    HP_WATER_POWER_OFF,
    HP_WATER_POWER_ON,
    DeviceType,
    get_device_profile,
    is_v3_heat_pump,
)
from .entity import BaseEntity, setup_dynamic_entities

PARALLEL_UPDATES = 0


WATER_HEATER_DESCRIPTION = WaterHeaterEntityDescription(
    key="water_heater",
    translation_key="aux_water",
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: AuxCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the AUX water heater platform."""
    coordinator = entry.runtime_data

    def entities_for_device(device: AuxDevice) -> list[AuxWaterHeaterEntity]:
        if get_device_profile(device).device_type is DeviceType.HEAT_PUMP:
            entity = AuxWaterHeaterEntity(
                coordinator,
                device["endpointId"],
                entity_description=WATER_HEATER_DESCRIPTION,
            )
            return [entity]
        return []

    setup_dynamic_entities(entry, coordinator, async_add_entities, entities_for_device)


class AuxWaterHeaterEntity(BaseEntity, WaterHeaterEntity):
    """AUX Cloud water heater entity."""

    def __init__(
        self,
        coordinator: AuxCloudCoordinator,
        device_id: str,
        entity_description: WaterHeaterEntityDescription,
    ) -> None:
        super().__init__(coordinator, device_id, entity_description)

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = 0  # Minimum temperature in Celsius
        self._attr_max_temp = 75  # Maximum temperature in Celsius
        self._attr_target_temperature_step = 1

        self._attr_supported_features = (
            WaterHeaterEntityFeature.TARGET_TEMPERATURE
            | WaterHeaterEntityFeature.OPERATION_MODE
            | WaterHeaterEntityFeature.ON_OFF
        )

    @property
    def current_temperature(self) -> float | int | None:
        """Return the current water temperature."""
        value = self._get_device_params().get(HP_HOT_WATER_TANK_TEMPERATURE)
        if not isinstance(value, (int, float)):
            return None
        return value / 10 if is_v3_heat_pump(self._device) else value

    @property
    def target_temperature(self) -> float | None:
        """Return the target water temperature (C)."""
        value = self._get_device_params().get(HP_HOT_WATER_TEMPERATURE_TARGET)
        return value / 10 if isinstance(value, (int, float)) else None

    @property
    def current_operation(self) -> str | None:
        """Return the current operation mode."""
        params = self._get_device_params()
        water_power = params.get(HP_WATER_POWER)
        fast_hotwater = params.get(HP_WATER_FAST_HOTWATER)

        if water_power is None:
            return None
        if water_power == 0:
            return STATE_OFF
        if fast_hotwater is None:
            return None
        if water_power == 1 and fast_hotwater == 1:
            return STATE_PERFORMANCE
        if water_power == 1:
            return STATE_HEAT_PUMP

        return None

    @property
    def operation_list(self) -> list[str]:
        """Return the list of available operation modes."""
        return [STATE_OFF, STATE_HEAT_PUMP, STATE_PERFORMANCE]

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target water temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._set_device_params(
                {HP_HOT_WATER_TEMPERATURE_TARGET: int(temperature * 10)}
            )

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set the operation mode."""
        if operation_mode == STATE_OFF:
            await self._set_device_params(
                {**HP_WATER_POWER_OFF, **HP_WATER_FAST_HOTWATER_OFF}
            )
        elif operation_mode == STATE_HEAT_PUMP:
            await self._set_device_params(
                {**HP_WATER_POWER_ON, **HP_WATER_FAST_HOTWATER_OFF}
            )
        elif operation_mode == STATE_PERFORMANCE:
            await self._set_device_params(
                {**HP_WATER_POWER_ON, **HP_WATER_FAST_HOTWATER_ON}
            )
        else:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_operation",
                translation_placeholders={"operation": operation_mode},
            )

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn the water heater on."""
        await self._set_device_params(HP_WATER_POWER_ON)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn the water heater off."""
        await self._set_device_params(HP_WATER_POWER_OFF)
