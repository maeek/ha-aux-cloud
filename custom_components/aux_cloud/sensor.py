"""Support for AUX Cloud sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.aux_cloud.api.const import AUX_MODEL_TO_NAME

from .const import DOMAIN, _LOGGER


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AUX Cloud sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities = []

    _LOGGER.debug(f"Setting up AUX Cloud sensors {coordinator.data['devices']}")

    for device in coordinator.data["devices"]:
        if 'params' in device and 'envtemp' in device['params']:
            entities.append(AuxCloudTemperatureSensor(coordinator, device['endpointId'], 'ambient_temperature', lambda d: d['params']['envtemp'] / 10))
        if 'params' in device and 'hp_water_tank_temp' in device['params']:
            entities.append(AuxCloudTemperatureSensor(coordinator, device['endpointId'], 'water_tank_temperature', lambda d: d['params']['hp_water_tank_temp']))
        if 'params' in device and 'hp_hotwater_temp' in device['params']:
            entities.append(AuxCloudTemperatureSensor(coordinator, device['endpointId'], 'hp_hotwater_temp', lambda d: d['params']['hp_hotwater_temp'] / 10))
        if 'params' in device and 'ac_temp' in device['params']:
            entities.append(AuxCloudTemperatureSensor(coordinator, device['endpointId'], 'ac_temp', lambda d: d['params']['ac_temp'] / 10))

    async_add_entities(entities, True)


class AuxCloudTemperatureSensor(SensorEntity, CoordinatorEntity):
    """Representation of an AUX Cloud temperature sensor."""

    def __init__(self, coordinator, device_id, param_name, get_value_fn):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._param_name = param_name
        self._get_value_fn = get_value_fn
        self._attr_name = f"{coordinator.get_device_by_endpoint_id(device_id)['friendlyName']} {param_name}"
        self._attr_unique_id = f"{device_id}_{param_name}"
        self._attr_native_unit_of_measurement = "°C"
        self._attr_device_class = "temperature"
        self.entity_id = f"sensor.{self._attr_unique_id}"
    
    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device info."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self.coordinator.get_device_by_endpoint_id(self._device_id)["friendlyName"],
            "connections": {(CONNECTION_NETWORK_MAC, self.coordinator.get_device_by_endpoint_id(self._device_id)["mac"])},
            "manufacturer": "AUX",
            "model": AUX_MODEL_TO_NAME[self.coordinator.get_device_by_endpoint_id(self._device_id)["productId"]] or 'Unknown',
        }

    @property
    def unique_id(self):
        """Return the unique ID of the sensor."""
        return self._attr_unique_id

    @property
    def native_value(self):
        """Return the state of the sensor."""
        _LOGGER.debug("Reading AUX Cloud sensor value for %s value is %s", self.coordinator.get_device_by_endpoint_id(self._device_id)["friendlyName"], self._get_value_fn(self._device))
        return self._get_value_fn(self.coordinator.get_device_by_endpoint_id(self._device_id))

    async def async_update(self):
        """Get the latest data."""
        _LOGGER.debug("Updating AUX Cloud sensor")
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    @property 
    def state(self):
        # Use the latest data from the coordinator
        return self._get_value_fn(self.coordinator.get_device_by_endpoint_id(self._device_id))