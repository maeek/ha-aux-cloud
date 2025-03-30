"""Support for AUX Cloud sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, _LOGGER
from datetime import datetime


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AUX Cloud sensor platform."""
    data = hass.data[DOMAIN]

    if not data.devices:
        return

    entities = []

    _LOGGER.warning(data.devices)

    # Add sensor entities for each thermostat
    for device in data.devices:
        if 'params' in device and 'envtemp' in device['params']:
            entities.append(AuxCloudTemperatureSensor(data, device, 'ambient_temperature', lambda d: d['params']['envtemp'] / 10))
        if 'params' in device and 'hp_water_tank_temp' in device['params']:
            entities.append(AuxCloudTemperatureSensor(data, device, 'water_tank_temperature', lambda d: d['params']['hp_water_tank_temp']))

    async_add_entities(entities, True)


class AuxCloudTemperatureSensor(SensorEntity):
    """Representation of an AUX Cloud temperature sensor."""

    def __init__(self, data, device, param_name, get_value_fn):
        """Initialize the sensor."""
        self._data = data
        self._device = device
        self._param_name = param_name
        self._get_value_fn = get_value_fn
        self._attr_name = f"{device['friendlyName']} {param_name}"
        self._attr_unique_id = f"{device['endpointId']}_{param_name}"
        self._attr_native_unit_of_measurement = "°C"
        self._attr_device_class = "temperature"
    
    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device info."""
        return {
            "identifiers": {(DOMAIN, self._device["endpointId"])},
            "name": self._device["friendlyName"],
            "connections": {(CONNECTION_NETWORK_MAC, self._device["mac"])},
            "manufacturer": "AUX",
            "model": self._device["productId"],
        }
    
    @property
    def unique_id(self):
        """Return the unique ID of the sensor."""
        return self._attr_unique_id

    @property
    def native_value(self):
        """Return the state of the sensor."""
        _LOGGER.debug("Reading AUX Cloud sensor value for %s value is %s", self._device["friendlyName"], self._get_value_fn(self._device))
        return self._get_value_fn(self._device)

    async def async_update(self):
        """Get the latest data."""
        _LOGGER.debug("Updating AUX Cloud sensor")
        await self._data.refresh()

        updated_device = next(
            (device for device in self._data.devices if device["endpointId"] == self._device["endpointId"]),
            None,
        )
        if updated_device:
            self._device = updated_device
