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

from .api.const import (
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

    # Create water heater entities for each device
    for device in coordinator.data["devices"]:
        for entity in WATER_HEATER_ENTITIES.values():
            # Only add water heater entities for devices that are in the AUX "Heat pump" category
            if device["productId"] in AuxProducts.DeviceType.HEAT_PUMP:
                entities.append(
                    AuxWaterHeaterEntity(
                        coordinator,
                        device["endpointId"],
                        entity_description=entity["description"],
                    )
                )
                _LOGGER.debug(
                    "Adding water heater entity for %s",
                    device["friendlyName"],
                )

    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.info("No AUX water heater devices added")


# pylint: disable=abstract-method
class AuxWaterHeaterEntity(BaseEntity, CoordinatorEntity, WaterHeaterEntity):
    """AUX Cloud water heater entity."""

    def __init__(
        self,
        coordinator,
        device_id,
        entity_description: WaterHeaterEntityDescription,
    ):
        """Initialize the water heater entity."""
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
        return self._get_device_params().get(HP_HOT_WATER_TANK_TEMPERATURE, 0)

    @property
    def target_temperature(self):
        """Return the target water temperature."""
        return self._get_device_params().get(HP_HOT_WATER_TEMPERATURE_TARGET, 0) / 10

    @property
    def current_operation(self):
        """Return the current operation mode."""
        if self._get_device_params().get(HP_WATER_POWER, 0) == 0:
            return STATE_OFF
        if self._get_device_params().get(HP_WATER_POWER, 0) == 1:
            return STATE_HEAT_PUMP
        if (
            self._get_device_params().get(HP_WATER_POWER, 0) == 1
            and self._get_device_params().get(HP_WATER_FAST_HOTWATER, 0) == 1
        ):
            return STATE_PERFORMANCE
        return STATE_OFF

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

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return [STATE_OFF, STATE_HEAT_PUMP, STATE_PERFORMANCE]

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "current_temperature": self.current_temperature,
            "target_temperature": self.target_temperature,
            "operation_mode": self.current_operation,
            "quiet_mode": self._get_device_params().get(HP_QUIET_MODE, 0),
            "ecomode": self._get_device_params().get(AUX_ECOMODE, 0),
        }

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the water heater on."""
        await self._set_device_params(HP_WATER_POWER_ON)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the water heater off."""
        await self._set_device_params(HP_WATER_POWER_OFF)
