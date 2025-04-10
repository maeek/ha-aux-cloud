"""Support for AUX Cloud sensors."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.aux_cloud.api.const import (
    AC_TEMPERATURE_AMBIENT,
    AC_TEMPERATURE_TARGET,
    AUX_ERROR_FLAG,
    AUX_MODEL_PARAMS_LIST,
    AUX_MODEL_SPECIAL_PARAMS_LIST,
    HP_HOT_WATER_TANK_TEMPERATURE,
    HP_HOT_WATER_TEMPERATURE_TARGET,
    HP_HEATER_TEMPERATURE_TARGET,
)
from custom_components.aux_cloud.util import BaseEntity
from .const import DOMAIN, _LOGGER

SENSORS: dict[str, dict[str, any]] = {
    AC_TEMPERATURE_AMBIENT: {
        "type": "temperature",
        "param": AC_TEMPERATURE_AMBIENT,
        "description": SensorEntityDescription(
            key=AC_TEMPERATURE_AMBIENT,
            name="Ambient Temperature",
            icon="mdi:thermometer",
            translation_key="ambient_temperature",
            device_class="temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        "get_fn": lambda d: d.get("params", {}).get(AC_TEMPERATURE_AMBIENT, 0) / 10,
    },
    HP_HOT_WATER_TANK_TEMPERATURE: {
        "type": "temperature",
        "param": HP_HOT_WATER_TANK_TEMPERATURE,
        "description": SensorEntityDescription(
            key=HP_HOT_WATER_TANK_TEMPERATURE,
            name="Water Tank Temperature",
            icon="mdi:thermometer-water",
            translation_key="water_tank_temperature",
            device_class="temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        "get_fn": lambda d: d.get("params", {}).get(HP_HOT_WATER_TANK_TEMPERATURE, 0),
    },
    HP_HOT_WATER_TEMPERATURE_TARGET: {
        "type": "temperature",
        "param": HP_HOT_WATER_TEMPERATURE_TARGET,
        "description": SensorEntityDescription(
            key=HP_HOT_WATER_TEMPERATURE_TARGET,
            name="Hot Water Temperature",
            icon="mdi:thermometer-water",
            translation_key="hot_water_temperature",
            device_class="temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        "get_fn": lambda d: d.get("params", {}).get(HP_HOT_WATER_TEMPERATURE_TARGET, 0)
        / 10,
    },
    AC_TEMPERATURE_TARGET: {
        "type": "temperature",
        "param": AC_TEMPERATURE_TARGET,
        "description": SensorEntityDescription(
            key=AC_TEMPERATURE_TARGET,
            name="AC Target Temperature",
            icon="mdi:home-thermometer",
            translation_key="ac_temperature",
            device_class="temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        "get_fn": lambda d: d.get("params", {}).get(AC_TEMPERATURE_TARGET, 0) / 10,
    },
    HP_HEATER_TEMPERATURE_TARGET: {
        "type": "temperature",
        "param": HP_HEATER_TEMPERATURE_TARGET,
        "description": SensorEntityDescription(
            key=HP_HEATER_TEMPERATURE_TARGET,
            name="HP Target Temperature",
            icon="mdi:home-thermometer",
            translation_key="ac_temperature",
            device_class="temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        "get_fn": lambda d: d.get("params", {}).get(HP_HEATER_TEMPERATURE_TARGET, 0)
        / 10,
    },
    AUX_ERROR_FLAG: {
        "type": "diagnostic",
        "param": AUX_ERROR_FLAG,
        "description": SensorEntityDescription(
            key=AUX_ERROR_FLAG,
            name="Error Flag",
            icon="mdi:alert-circle",
            translation_key="err_flag",
            device_class="diagnostic",
        ),
        "get_fn": lambda d: d.get("params", {}).get(AUX_ERROR_FLAG, None),
    },
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

    _LOGGER.debug("Setting up AUX Cloud sensors %s", coordinator.data["devices"])
    for device in coordinator.data["devices"]:
        for entity in SENSORS.values():
            if "productId" in device and (
                (
                    device["productId"] in AUX_MODEL_PARAMS_LIST
                    and entity["param"]
                    in AUX_MODEL_PARAMS_LIST.get(device["productId"])
                )
                or (
                    device["productId"] in AUX_MODEL_SPECIAL_PARAMS_LIST
                    and entity["param"]
                    in AUX_MODEL_SPECIAL_PARAMS_LIST.get(device["productId"])
                )
            ):
                sensor = AuxCloudSensor(
                    coordinator,
                    device["endpointId"],
                    entity["description"],
                    entity["get_fn"],
                )
                entities.append(sensor)
                _LOGGER.debug(
                    "Adding sensor entity for %s with unique_id %s",
                    device["friendlyName"],
                    sensor.unique_id,
                )

    async_add_entities(entities, True)


class AuxCloudSensor(BaseEntity, CoordinatorEntity, SensorEntity):
    """Representation of an AUX Cloud temperature sensor."""

    def __init__(self, coordinator, device_id, entity_description, get_value_fn):
        """Initialize the sensor."""
        super().__init__(coordinator, device_id, entity_description)
        self._get_value_fn = get_value_fn
        self.entity_id = f"sensor.{self._attr_unique_id}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self._device is None:
            return None

        return self._get_value_fn(self._device)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.native_value
