"""Support for AUX Cloud sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api.models import AuxDevice
from .coordinator import AuxCloudConfigEntry
from .devices import (
    AC_TEMPERATURE_AMBIENT,
    AC_TEMPERATURE_TARGET,
    AUX_ERROR_FLAG,
    HP_HEATER_TEMPERATURE_TARGET,
    HP_HOT_WATER_TANK_TEMPERATURE,
    HP_HOT_WATER_TEMPERATURE_TARGET,
    is_v3_heat_pump,
)
from .entity import BaseEntity, setup_dynamic_entities, supported_entity_descriptions

PARALLEL_UPDATES = 0


def _scaled_param(device: AuxDevice, key: str, divisor: int = 10) -> float | int | None:
    """Return a scaled parameter or None when the cloud omitted it."""
    value = device.get("params", {}).get(key)
    return value / divisor if value is not None else None


@dataclass(frozen=True, kw_only=True)
class AuxSensorEntityDescription(SensorEntityDescription):
    """Describe an AUX sensor and how to derive its native value."""

    value_fn: Callable[[AuxDevice], Any]


SENSORS = {
    AC_TEMPERATURE_AMBIENT: AuxSensorEntityDescription(
        key=AC_TEMPERATURE_AMBIENT,
        translation_key="ambient_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _scaled_param(d, AC_TEMPERATURE_AMBIENT),
    ),
    HP_HOT_WATER_TANK_TEMPERATURE: AuxSensorEntityDescription(
        key=HP_HOT_WATER_TANK_TEMPERATURE,
        translation_key="water_tank_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _scaled_param(
            d,
            HP_HOT_WATER_TANK_TEMPERATURE,
            10 if is_v3_heat_pump(d) else 1,
        ),
    ),
    HP_HOT_WATER_TEMPERATURE_TARGET: AuxSensorEntityDescription(
        key=HP_HOT_WATER_TEMPERATURE_TARGET,
        translation_key="hot_water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _scaled_param(d, HP_HOT_WATER_TEMPERATURE_TARGET),
    ),
    AC_TEMPERATURE_TARGET: AuxSensorEntityDescription(
        key=AC_TEMPERATURE_TARGET,
        translation_key="ac_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _scaled_param(d, AC_TEMPERATURE_TARGET),
    ),
    HP_HEATER_TEMPERATURE_TARGET: AuxSensorEntityDescription(
        key=HP_HEATER_TEMPERATURE_TARGET,
        translation_key="ac_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _scaled_param(d, HP_HEATER_TEMPERATURE_TARGET),
    ),
    AUX_ERROR_FLAG: AuxSensorEntityDescription(
        key=AUX_ERROR_FLAG,
        translation_key="err_flag",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("params", {}).get(AUX_ERROR_FLAG),
    ),
}


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: AuxCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AUX Cloud sensors."""
    coordinator = entry.runtime_data

    def entities_for_device(device: AuxDevice) -> list[AuxCloudSensor]:
        return [
            AuxCloudSensor(
                coordinator,
                device["endpointId"],
                entity,
            )
            for entity in supported_entity_descriptions(device, SENSORS.values())
        ]

    setup_dynamic_entities(entry, coordinator, async_add_entities, entities_for_device)


class AuxCloudSensor(BaseEntity, SensorEntity):
    """Representation of an AUX Cloud temperature sensor."""

    entity_description: AuxSensorEntityDescription

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self._device)
