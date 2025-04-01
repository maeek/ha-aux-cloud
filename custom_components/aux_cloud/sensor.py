"""Support for AUX Cloud sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.aux_cloud.util import BaseEntity

from .const import DOMAIN, _LOGGER

SENSORS: dict[str, dict[str, any]] = {
    "ambient_temperature": {
        "type": "temperature",
        "required_params": ["envtemp"],
        "description": SensorEntityDescription(
            key="ambient_temperature",
            name="Ambient Temperature",
            icon="mdi:thermometer",
            translation_key="ambient_temperature",
            device_class="temperature",
            native_unit_of_measurement="°C",
        ),
        "get_fn": lambda d: d["params"]["envtemp"] / 10,
    },
    "water_tank_temperature": {
        "type": "temperature",
        "required_params": ["hp_water_tank_temp"],
        "description": SensorEntityDescription(
            key="water_tank_temperature",
            name="Water Tank Temperature",
            icon="mdi:water-boiler",
            translation_key="water_tank_temperature",
            device_class="temperature",
            native_unit_of_measurement="°C",
        ),
        "get_fn": lambda d: d["params"]["hp_water_tank_temp"],
    },
    "hp_hotwater_temp": {
        "type": "temperature",
        "required_params": ["hp_hotwater_temp"],
        "description": SensorEntityDescription(
            key="hot_water_temperature",
            name="Hot Water Temperature",
            icon="mdi:water-boiler",
            translation_key="hot_water_temperature",
            device_class="temperature",
            native_unit_of_measurement="°C",
        ),
        "get_fn": lambda d: d["params"]["hp_hotwater_temp"] / 10,
    },
    "ac_temp": {
        "type": "temperature",
        "required_params": ["ac_temp"],
        "description": SensorEntityDescription(
            key="ac_temperature",
            name="AC Temperature",
            icon="mdi:thermometer",
            translation_key="ac_temperature",
            device_class="temperature",
            native_unit_of_measurement="°C",
        ),
        "get_fn": lambda d: d["params"]["ac_temp"] / 10,
    },
    # Add more sensors as needed
}

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
        for entity in SENSORS.values():
            # Add temperature sensors
            if "params" in device and all(param in device["params"] for param in entity["required_params"]) and entity["type"] == "temperature":
                entities.append(
                    AuxCloudSensor(
                        coordinator,
                        device["endpointId"],
                        entity["description"],
                        entity["get_fn"]
                    )
                )
                _LOGGER.debug(f"Adding sensor entity for {device['friendlyName']} with option {entity['description'].key}")

    async_add_entities(entities, True)


class AuxCloudSensor(BaseEntity, SensorEntity, CoordinatorEntity):
    """Representation of an AUX Cloud temperature sensor."""

    def __init__(self, coordinator, device_id, entity_description, get_value_fn):
        """Initialize the sensor."""
        super().__init__(coordinator, device_id, entity_description)
        self._get_value_fn = get_value_fn
        self._attr_has_entity_name = True
        self.entity_id = f"sensor.{self._attr_unique_id}"
        self.entity_description = entity_description
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        _LOGGER.debug("Reading AUX Cloud sensor value for %s value is %s", self._get_device().get("friendlyName", "AUX"), self._get_value_fn(self._device_id))
        return self._get_value_fn(self._get_device())

    async def async_update(self):
        """Get the latest data."""
        _LOGGER.debug("Updating AUX Cloud sensor")
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    @property 
    def state(self):
        # Use the latest data from the coordinator
        return self._get_value_fn(self._get_device())