"""Water Heater platform for AUX Cloud integration."""

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from custom_components.aux_cloud.api.const import AUX_MODEL_TO_NAME

from .const import DOMAIN, _LOGGER


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
        if "hp_hotwater_temp" in device["params"]:
            entities.append(AuxWaterHeaterEntity(coordinator, device['endpointId']))

    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.info("No AUX water heater devices added")


class AuxWaterHeaterEntity(CoordinatorEntity, WaterHeaterEntity):
    """AUX Cloud water heater entity."""

    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, device_id):
        """Initialize the water heater entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_water_heater"
        self._attr_name = f"{coordinator.get_device_by_endpoint_id(device_id).get('friendlyName', 'AUX')} Water Heater"
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = 30  # Minimum temperature in Celsius
        self._attr_max_temp = 75  # Maximum temperature in Celsius

    @property
    def device_info(self):
        """Return the device info."""
        dev = self.coordinator.get_device_by_endpoint_id(self._device_id)
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "connections": {(CONNECTION_NETWORK_MAC, dev["mac"])} if "mac" in dev else None,
            "name": self._attr_name,
            "manufacturer": "AUX",
            "model": AUX_MODEL_TO_NAME[dev["productId"]] or "Unknown",
        }

    @property
    def current_temperature(self):
        """Return the current water temperature."""
        return self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("hp_water_tank_temp", None)

    @property
    def target_temperature(self):
        """Return the target water temperature."""
        return self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("hp_hotwater_temp", None) / 10

    @property
    def is_ecomode_on(self):
        """Return whether ecomode is on."""
        return self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("ecomode", 0) == 1

    @property
    def is_fast_hotwater_on(self):
        """Return whether fast hot water mode is on."""
        return self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("hp_fast_hotwater", 0) == 1
    
    @property
    def is_quiet_mode_on(self):
        """Return whether quiet mode is on."""
        return self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("qtmode", 0) == 1

    @property
    def current_operation(self):
        """Return the current operation mode."""
        if self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("hp_pwr", 0) == 0:
            return "off"
        if self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("hp_fast_hotwater", 0) == 1 and self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("hp_pwr", 0) == 1:
            return "fast_hotwater"
        if self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("ecomode", 0) == 1 and self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("hp_pwr", 0) == 1:
            return "eco"
        if self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("qtmode", 0) == 1 and self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("hp_pwr", 0) == 1:
            return "quiet"
        return "normal"

    async def async_set_temperature(self, **kwargs):
        """Set new target water temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._set_device_param({"hp_hotwater_temp": int(temperature * 10)})

    async def async_set_operation_mode(self, operation_mode):
        """Set the operation mode."""
        if operation_mode == "off":
            await self._set_device_param({"hp_pwr": 0})
        elif operation_mode == "fast_hotwater":
            await self._set_device_param({"hp_fast_hotwater": 1, "ecomode": 0, "hp_pwr": 1})
        elif operation_mode == "eco":
            await self._set_device_param({"ecomode": 1, "hp_fast_hotwater": 0, "hp_pwr": 1})
        elif operation_mode == "quiet":
            await self._set_device_param({"qtmode": 1, "hp_fast_hotwater": 0, "hp_pwr": 1})
        elif operation_mode == "normal":
            await self._set_device_param({"ecomode": 0, "hp_fast_hotwater": 0, "hp_pwr": 1, "qtmode": 0})

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return ["off", "normal", "eco", "quiet", "fast_hotwater"]

    async def async_turn_on(self):
        """Turn the water heater on."""
        await self._set_device_param({"hp_pwr": 1})

    async def async_turn_off(self):
        """Turn the water heater off."""
        await self._set_device_param({"hp_pwr": 0})

    async def async_turn_on_ecomode(self):
        """Turn on ecomode."""
        await self._set_device_param({"ecomode": 1})

    async def async_turn_off_ecomode(self):
        """Turn off ecomode."""
        await self._set_device_param({"ecomode": 0})

    async def async_turn_on_fast_hotwater(self):
        """Turn on fast hot water mode."""
        await self._set_device_param({"hp_fast_hotwater": 1})

    async def async_turn_off_fast_hotwater(self):
        """Turn off fast hot water mode."""
        await self._set_device_param({"hp_fast_hotwater": 0})

    async def _set_device_param(self, params):
        """Set parameters on the device."""
        _LOGGER.debug("Setting %s for device %s", params, self.coordinator.get_device_by_endpoint_id(self._device_id)["friendlyName"])
        await self.coordinator.api.set_device_params(self.coordinator.get_device_by_endpoint_id(self._device_id), params)
        await self.coordinator.async_request_refresh()