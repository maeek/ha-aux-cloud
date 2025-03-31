from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
    WaterHeaterEntityEntityDescription,
    STATE_HEAT_PUMP,
    STATE_OFF,
    STATE_PERFORMANCE
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.aux_cloud.util import BaseEntity

from .const import DOMAIN, _LOGGER

WATER_HEATER_ENTITIES: dict[str, dict[str, any]] = {
  "water_heater": {
    "required_params": ["hp_hotwater_temp", "hp_pwr", "hp_water_tank_temp"],
    "description": WaterHeaterEntityEntityDescription(
        key="water_heater",
        name="Water Heater",
        icon="mdi:water-boiler",
        translation_key="aux_water"
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
            if "params" in device and all(param in device["params"] for param in entity["required_params"]):
                entities.append(
                    AuxWaterHeaterEntity(
                        coordinator,
                        device["endpointId"],
                        entity_description=entity["description"]
                    )
                )
                _LOGGER.debug(f"Adding water heater entity for {device['friendlyName']}")
            

    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.info("No AUX water heater devices added")


class AuxWaterHeaterEntity(BaseEntity, CoordinatorEntity, WaterHeaterEntity):
    """AUX Cloud water heater entity."""


    def __init__(self, coordinator, device_id, entity_description: WaterHeaterEntityEntityDescription):
        """Initialize the water heater entity."""
        super().__init__(coordinator, device_id, entity_description)
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = 0  # Minimum temperature in Celsius
        self._attr_max_temp = 75  # Maximum temperature in Celsius
        self._attr_supported_features = (
            WaterHeaterEntityFeature.TARGET_TEMPERATURE
            | WaterHeaterEntityFeature.OPERATION_MODE
            | WaterHeaterEntityFeature.ON_OFF
        )
        self.entity_id = f"water_heater.{self._attr_unique_id}"

    @property
    def current_temperature(self):
        """Return the current water temperature."""
        return self.coordinator.get_device_by_endpoint_id(self._device_id).get("params", {}).get("hp_water_tank_temp", None)

    @property
    def target_temperature(self):
        """Return the target water temperature."""
        return self.coordinator.get_device_by_endpoint_id(self._device_id).get("params", {}).get("hp_hotwater_temp", None) / 10

    @property
    def current_operation(self):
        """Return the current operation mode."""
        if self.coordinator.get_device_by_endpoint_id(self._device_id).get("params", {}).get("hp_pwr", 0) == 0:
            return STATE_OFF
        if self.coordinator.get_device_by_endpoint_id(self._device_id).get("params", {}).get("hp_pwr", 0) == 1:
            return STATE_HEAT_PUMP
        if (
            self.coordinator.get_device_by_endpoint_id(self._device_id).get("params", {}).get("hp_pwr", 0) == 1 and
            self.coordinator.get_device_by_endpoint_id(self._device_id).get("params", {}).get("hp_fast_hotwater", 0) == 1
        ):
            return STATE_PERFORMANCE
        return STATE_OFF

    async def async_set_temperature(self, **kwargs):
        """Set new target water temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._set_device_params({"hp_hotwater_temp": int(temperature * 10)})

    async def async_set_operation_mode(self, operation_mode):
        """Set the operation mode."""
        if operation_mode == STATE_OFF:
            await self._set_device_params({"hp_pwr": 0, "hp_fast_hotwater": 0})
        elif operation_mode == STATE_HEAT_PUMP:
            await self._set_device_params({"hp_pwr": 1, "hp_fast_hotwater": 0})
        elif operation_mode == STATE_PERFORMANCE:
            await self._set_device_params({"hp_pwr": 1, "hp_fast_hotwater": 1})

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
            "quiet_mode": self.coordinator.get_device_by_endpoint_id(self._device_id).get("params", {}).get("qtmode", 0),
            "eco_mode": self.coordinator.get_device_by_endpoint_id(self._device_id).get("params", {}).get("ecomode", 0)
        }

    async def async_turn_on(self):
        """Turn the water heater on."""
        await self._set_device_params({"hp_pwr": 1})

    async def async_turn_off(self):
        """Turn the water heater off."""
        await self._set_device_params({"hp_pwr": 0})
