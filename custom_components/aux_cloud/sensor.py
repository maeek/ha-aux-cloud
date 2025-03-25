"""Support for AUX Cloud sensors."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api.const import AUX_MODELS
from .const import DOMAIN, _LOGGER, MANUFACTURER


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
            _LOGGER.debug("Skipping offline device: %s", device.get('friendlyName', 'Unknown'))
            continue

        # Get device parameters
        params = device.get('params', {})
        product_id = device.get('productId', '')

        # Determine device type
        device_type = "unknown"
        if product_id in AUX_MODELS:
            device_type = AUX_MODELS[product_id].get('type', 'unknown')

        _LOGGER.debug("Setting up device type: %s with ID: %s", device_type, product_id)

        # Add environment temperature sensor if available (works for both AC and heat pumps)
        if 'envtemp' in params:
            entities.append(AuxCloudTemperatureSensor(data, device))

        # Add setpoint temperature sensor based on device type
        if device_type == "heat_pump" and 'hp_hotwater_temp' in params:
            entities.append(AuxCloudSetpointSensor(data, device, "hp_hotwater_temp", "Hot Water Target"))
        elif device_type == "air_conditioner" and 'ac_temp' in params:
            entities.append(AuxCloudSetpointSensor(data, device, "ac_temp", "Target"))
        elif 'temp' in params:  # Generic fallback
            entities.append(AuxCloudSetpointSensor(data, device, "temp", "Target"))

        # Heat pump specific sensors
        if device_type == "heat_pump":
            if 'hp_water_tank_temp' in params:
                entities.append(AuxCloudWaterTankSensor(data, device))

        # Air conditioner specific sensors
        if device_type == "air_conditioner":
            # Mode sensor
            if 'ac_mode' in params:
                entities.append(AuxCloudModeSensor(data, device))

            # Fan speed sensor
            if 'ac_mark' in params:
                entities.append(AuxCloudFanSpeedSensor(data, device))

    if entities:
        _LOGGER.debug("Adding %d sensor entities", len(entities))
        async_add_entities(entities, True)
    else:
        _LOGGER.warning("No AUX Cloud sensor entities created")


class AuxBaseSensor(SensorEntity):
    """Base class for all AUX Cloud sensors."""

    def __init__(self, data, device, unique_suffix="sensor"):
        """Initialize the base sensor."""
        self._data = data
        self._device = device
        self._attr_unique_id = f"{device['endpointId']}_{unique_suffix}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device['endpointId'])},
            "name": device.get('friendlyName', 'AUX Device'),
            "manufacturer": MANUFACTURER,
            "model": self._get_model_name(device),
        }

    def _get_model_name(self, device):
        """Get model name based on product ID."""
        product_id = device.get('productId', '')
        if product_id in AUX_MODELS:
            device_type = AUX_MODELS[product_id].get('type', 'unknown')
            return f"AUX {device_type.replace('_', ' ').title()}"
        return "AUX Device"

    async def async_update(self):
        """Get the latest data."""
        await self._data.update()

        # Find the updated device data
        for device in self._data.devices:
            if device['endpointId'] == self._device['endpointId']:
                self._device = device
                break


class AuxCloudTemperatureSensor(AuxBaseSensor):
    """Representation of an AUX Cloud temperature sensor."""

    def __init__(self, data, device):
        """Initialize the temperature sensor."""
        super().__init__(data, device, "temperature")
        self._attr_name = f"{device.get('friendlyName', 'AUX Device')} Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

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


class AuxCloudWaterTankSensor(AuxBaseSensor):
    """Representation of an AUX Cloud water tank temperature sensor."""

    def __init__(self, data, device):
        """Initialize the water tank sensor."""
        super().__init__(data, device, "water_tank_temperature")
        self._attr_name = f"{device.get('friendlyName', 'AUX Device')} Water Tank Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return the state of the sensor."""
        params = self._device.get('params', {})
        if 'hp_water_tank_temp' in params:
            return params['hp_water_tank_temp']
        return None


class AuxCloudSetpointSensor(AuxBaseSensor):
    """Representation of an AUX Cloud temperature setpoint sensor."""

    def __init__(self, data, device, param_name, name_suffix):
        """Initialize the setpoint sensor."""
        super().__init__(data, device, f"{param_name}_setpoint")
        self._param_name = param_name
        self._attr_name = f"{device.get('friendlyName', 'AUX Device')} {name_suffix} Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        """Return the state of the sensor."""
        params = self._device.get('params', {})
        if self._param_name in params:
            temp = params[self._param_name]
            # If temperature is stored as an integer but represents tenths of degrees
            if temp > 100:
                return temp / 10
            return temp
        return None


class AuxCloudModeSensor(AuxBaseSensor):
    """Representation of an AUX Cloud mode sensor."""

    _modes = {
        0: "Auto",
        1: "Cool",
        2: "Dry",
        3: "Fan Only",
        4: "Heat"
    }

    def __init__(self, data, device):
        """Initialize the mode sensor."""
        super().__init__(data, device, "mode")
        self._attr_name = f"{device.get('friendlyName', 'AUX Device')} Mode"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        """Return the state of the sensor."""
        params = self._device.get('params', {})
        if 'ac_mode' in params:
            mode_number = params['ac_mode']
            return self._modes.get(mode_number, f"Unknown ({mode_number})")
        return None


class AuxCloudFanSpeedSensor(AuxBaseSensor):
    """Representation of an AUX Cloud fan speed sensor."""

    _fan_speeds = {
        0: "Auto",
        1: "Low",
        2: "Medium",
        3: "High",
        4: "Turbo",
        5: "Quiet"
    }

    def __init__(self, data, device):
        """Initialize the fan speed sensor."""
        super().__init__(data, device, "fan_speed")
        self._attr_name = f"{device.get('friendlyName', 'AUX Device')} Fan Speed"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        """Return the state of the sensor."""
        params = self._device.get('params', {})
        if 'ac_mark' in params:
            speed_number = params['ac_mark']
            return self._fan_speeds.get(speed_number, f"Unknown ({speed_number})")
        return None
