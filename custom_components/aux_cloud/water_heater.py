from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
    WaterHeaterEntityDescription,
    STATE_HEAT_PUMP,
    STATE_OFF,
    STATE_PERFORMANCE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .devices.profiles import (
    AuxProducts,
    AUX_ECOMODE,
    HP_HOT_WATER_TANK_TEMPERATURE,
    HP_HOT_WATER_TEMPERATURE_TARGET,
    HP_WATER_FAST_HOTWATER,
    HP_WATER_FAST_HOTWATER_OFF,
    HP_WATER_FAST_HOTWATER_ON,
    HP_WATER_POWER,
    HP_WATER_POWER_OFF,
    HP_WATER_POWER_ON,
    HP_QUIET_MODE,
)
from .const import DOMAIN, _LOGGER
from .util import BaseEntity


WATER_HEATER_ENTITIES: dict[str, dict[str, any]] = {
    "water_heater": {
        "description": WaterHeaterEntityDescription(
            key="water_heater",
            name="Water Heater",
            icon="mdi:water-boiler",
            translation_key="aux_water",
        )
    }
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AUX water heater platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities = []

    for device in coordinator.data["devices"]:
        if device["productId"] in AuxProducts.DeviceType.HEAT_PUMP:
            entities.append(
                AuxWaterHeaterEntity(
                    coordinator,
                    device["endpointId"],
                    entity_description=WATER_HEATER_ENTITIES["water_heater"][
                        "description"
                    ],
                )
            )
            _LOGGER.debug(
                "Adding water heater entity for %s",
                device.get("friendlyName", device["endpointId"]),
            )

    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.info("No AUX water heater devices added")


class AuxWaterHeaterEntity(BaseEntity, CoordinatorEntity, WaterHeaterEntity):
    """AUX Cloud water heater entity."""

    def __init__(
        self,
        coordinator,
        device_id: str,
        entity_description: WaterHeaterEntityDescription,
    ):
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

        self.entity_id = f"water_heater.{self._attr_unique_id}"

    @property
    def current_temperature(self):
        """Return the current water temperature."""
        value = self._get_device_params().get(HP_HOT_WATER_TANK_TEMPERATURE, 0)
        return value / 10 if AuxProducts.is_v3_heat_pump(self._device) else value

    @property
    def target_temperature(self):
        """Return the target water temperature (C)."""
        value = self._get_device_params().get(HP_HOT_WATER_TEMPERATURE_TARGET)
        return value / 10 if value is not None else None

    @property
    def current_operation(self):
        """Return the current operation mode."""
        water_power = self._get_device_params().get(HP_WATER_POWER, 0)
        fast_hotwater = self._get_device_params().get(HP_WATER_FAST_HOTWATER, 0)

        if water_power == 0:
            return STATE_OFF
        if water_power == 1 and fast_hotwater == 1:
            return STATE_PERFORMANCE
        if water_power == 1:
            return STATE_HEAT_PUMP

        return STATE_OFF

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return [STATE_OFF, STATE_HEAT_PUMP, STATE_PERFORMANCE]

    async def async_set_temperature(self, **kwargs):
        """Set a new target water temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._set_device_params(
                {HP_HOT_WATER_TEMPERATURE_TARGET: int(temperature * 10)}
            )

    async def async_set_operation_mode(self, operation_mode):
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

    async def async_turn_on(self, **kwargs):
        """Turn the water heater on."""
        await self._set_device_params(HP_WATER_POWER_ON)

    async def async_turn_off(self, **kwargs):
        """Turn the water heater off."""
        await self._set_device_params(HP_WATER_POWER_OFF)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        return {
            "current_temperature": self.current_temperature,
            "target_temperature": self.target_temperature,
            "operation_mode": self.current_operation,
            "quiet_mode": self._get_device_params().get(HP_QUIET_MODE, 0),
            "ecomode": self._get_device_params().get(AUX_ECOMODE, 0),
        }
