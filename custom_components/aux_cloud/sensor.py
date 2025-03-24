"""Support for AUX Cloud sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
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
        _LOGGER.warning("No AUX Cloud devices found")
        return

    entities = []

    # Add sensor entities for each device
    for device in data.devices:
        # Skip devices that are offline
        if device.get('state', 0) != 1:
            continue

        # Add temperature sensors if the device has temperature parameters
        params = device.get('params', {})

        # Check if this is a heat pump with tank temperature
        if 'hp_water_tank_temp' in params:
            entities.append(AuxCloudWaterTankSensor(data, device))

        # Add room temperature sensor if available
        if 'envtemp' in params:
            entities.append(AuxCloudTemperatureSensor(data, device))

        # For devices with AC temperature setpoint
        if 'ac_temp' in params:
            entities.append(AuxCloudSetpointSensor(data, device))

        # You can add more sensor types based on your device parameters

    if entities:
        _LOGGER.debug("Adding %d sensor entities", len(entities))
        async_add_entities(entities, True)
    else:
        _LOGGER.warning("No AUX Cloud sensor entities created")


class AuxCloudTemperatureSensor(SensorEntity):
    """Representation of an AUX Cloud temperature sensor."""

    def __init__(self, data, device):
        """Initialize the sensor."""
        self._data = data
        self._device = device
        self._attr_unique_id = f"{device['endpointId']}_temperature"
        self._attr_name = f"{device.get('friendlyName', 'AUX Device')} Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE

    @property
    def native_value(self):
        """Return the state of the sensor."""
        params = self._device.get('params', {})
        # Some devices store temperature as tenths of degrees
        if 'envtemp' in params:
            temp = params['envtemp']
            # If temperature is stored as an integer but represents tenths of degrees
            if temp > 100:
                return temp / 10
            return temp
        return None

    async def async_update(self):
        """Get the latest data."""
        await self._data.update()

        # Find the updated device data
        for device in self._data.devices:
            if device['endpointId'] == self._device['endpointId']:
                self._device = device
                break


class AuxCloudWaterTankSensor(SensorEntity):
    """Representation of an AUX Cloud water tank temperature sensor."""

    def __init__(self, data, device):
        """Initialize the sensor."""
        self._data = data
        self._device = device
        self._attr_unique_id = f"{device['endpointId']}_water_tank_temperature"
        self._attr_name = f"{device.get('friendlyName', 'AUX Device')} Water Tank Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE

    @property
    def native_value(self):
        """Return the state of the sensor."""
        params = self._device.get('params', {})
        if 'hp_water_tank_temp' in params:
            return params['hp_water_tank_temp']
        return None

    async def async_update(self):
        """Get the latest data."""
        await self._data.update()

        # Find the updated device data
        for device in self._data.devices:
            if device['endpointId'] == self._device['endpointId']:
                self._device = device
                break


class AuxCloudSetpointSensor(SensorEntity):
    """Representation of an AUX Cloud temperature setpoint sensor."""

    def __init__(self, data, device):
        """Initialize the sensor."""
        self._data = data
        self._device = device
        self._attr_unique_id = f"{device['endpointId']}_setpoint"
        self._attr_name = f"{device.get('friendlyName', 'AUX Device')} Target Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        """Return the state of the sensor."""
        params = self._device.get('params', {})
        if 'ac_temp' in params:
            temp = params['ac_temp']
            # If temperature is stored as an integer but represents tenths of degrees
            if temp > 100:
                return temp / 10
            return temp
        return None

    async def async_update(self):
        """Get the latest data."""
        await self._data.update()

        # Find the updated device data
        for device in self._data.devices:
            if device['endpointId'] == self._device['endpointId']:
                self._device = device
                break
