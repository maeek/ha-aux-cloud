"""Support for AUX Cloud sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, _LOGGER


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

    # Add sensor entities for each thermostat
    for device in data.devices:
        if 'params' in device and 'envtemp' in device['params']:
            entities.append(AuxCloudTemperatureSensor(data, device))
        # Add other sensor types as needed

    async_add_entities(entities, True)


class AuxCloudTemperatureSensor(SensorEntity):
    """Representation of an AUX Cloud temperature sensor."""

    def __init__(self, data, thermostat):
        """Initialize the sensor."""
        self._data = data
        self._thermostat = thermostat
        self._attr_unique_id = f"{thermostat['endpointId']}_temperature"
        self._attr_name = f"{thermostat['friendlyName']} Ambient Temperature"
        self._attr_native_unit_of_measurement = "°C"
        self._attr_device_class = "temperature"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        # This should return the current temperature from your API
        # Modify this to match your actual API data structure
        return self._thermostat['params']['envtemp'] / 10

    async def async_update(self):
        """Get the latest data."""
        await self._data.update()
