"""Support for AUX Cloud sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .devices.profiles import (
    AC_TEMPERATURE_AMBIENT,
    AC_TEMPERATURE_TARGET,
    AUX_ERROR_FLAG,
    HP_HEATER_TEMPERATURE_TARGET,
    HP_HOT_WATER_TANK_TEMPERATURE,
    HP_HOT_WATER_TEMPERATURE_TARGET,
    AuxProducts,
)
from .util import BaseEntity, setup_dynamic_entities

PARALLEL_UPDATES = 0


def _scaled_param(device: dict[str, Any], key: str, divisor: int = 10):
    """Return a scaled parameter or None when the cloud omitted it."""
    value = device.get("params", {}).get(key)
    return value / divisor if value is not None else None


SENSORS: dict[str, dict[str, Any]] = {
    AC_TEMPERATURE_AMBIENT: {
        "type": "temperature",
        "param": AC_TEMPERATURE_AMBIENT,
        "description": SensorEntityDescription(
            key=AC_TEMPERATURE_AMBIENT,
            name="Ambient Temperature",
            icon="mdi:thermometer",
            translation_key="ambient_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        "get_fn": lambda d: _scaled_param(d, AC_TEMPERATURE_AMBIENT),
    },
    HP_HOT_WATER_TANK_TEMPERATURE: {
        "type": "temperature",
        "param": HP_HOT_WATER_TANK_TEMPERATURE,
        "description": SensorEntityDescription(
            key=HP_HOT_WATER_TANK_TEMPERATURE,
            name="Water Tank Temperature",
            icon="mdi:thermometer-water",
            translation_key="water_tank_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        "get_fn": lambda d: _scaled_param(
            d,
            HP_HOT_WATER_TANK_TEMPERATURE,
            10 if AuxProducts.is_v3_heat_pump(d) else 1,
        ),
    },
    HP_HOT_WATER_TEMPERATURE_TARGET: {
        "type": "temperature",
        "param": HP_HOT_WATER_TEMPERATURE_TARGET,
        "description": SensorEntityDescription(
            key=HP_HOT_WATER_TEMPERATURE_TARGET,
            name="Hot Water Temperature",
            icon="mdi:thermometer-water",
            translation_key="hot_water_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_registry_enabled_default=False,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        "get_fn": lambda d: _scaled_param(d, HP_HOT_WATER_TEMPERATURE_TARGET),
    },
    AC_TEMPERATURE_TARGET: {
        "type": "temperature",
        "param": AC_TEMPERATURE_TARGET,
        "description": SensorEntityDescription(
            key=AC_TEMPERATURE_TARGET,
            name="AC Target Temperature",
            icon="mdi:home-thermometer",
            translation_key="ac_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_registry_enabled_default=False,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        "get_fn": lambda d: _scaled_param(d, AC_TEMPERATURE_TARGET),
    },
    HP_HEATER_TEMPERATURE_TARGET: {
        "type": "temperature",
        "param": HP_HEATER_TEMPERATURE_TARGET,
        "description": SensorEntityDescription(
            key=HP_HEATER_TEMPERATURE_TARGET,
            name="HP Target Temperature",
            icon="mdi:home-thermometer",
            translation_key="ac_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_registry_enabled_default=False,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        "get_fn": lambda d: _scaled_param(d, HP_HEATER_TEMPERATURE_TARGET),
    },
    AUX_ERROR_FLAG: {
        "type": "diagnostic",
        "param": AUX_ERROR_FLAG,
        "description": SensorEntityDescription(
            key=AUX_ERROR_FLAG,
            name="Error Flag",
            icon="mdi:alert-circle",
            translation_key="err_flag",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
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
    coordinator = entry.runtime_data.coordinator

    def entities_for_device(device):
        entities = []
        supported_params = AuxProducts.get_params_list(device["productId"])
        supported_special_params = AuxProducts.get_special_params_list(
            device["productId"]
        )

        for entity in SENSORS.values():
            if "productId" in device and (
                (supported_params and entity["description"].key in supported_params)
                or (
                    supported_special_params
                    and entity["description"].key in supported_special_params
                )
            ):
                sensor = AuxCloudSensor(
                    coordinator,
                    device["endpointId"],
                    entity["description"],
                    entity["get_fn"],
                )
                entities.append(sensor)

        return entities

    setup_dynamic_entities(entry, coordinator, async_add_entities, entities_for_device)


class AuxCloudSensor(BaseEntity, SensorEntity):
    """Representation of an AUX Cloud temperature sensor."""

    def __init__(self, coordinator, device_id, entity_description, get_value_fn):
        """Initialize the sensor."""
        super().__init__(coordinator, device_id, entity_description)
        self._get_value_fn = get_value_fn

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self._device is None:
            return None

        return self._get_value_fn(
            {
                **self._device,
                "params": self._get_device_params(),
            }
        )
