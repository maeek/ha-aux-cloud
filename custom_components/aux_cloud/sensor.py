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
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api.models import AuxDevice, EnergyStatistics
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


@dataclass(frozen=True, kw_only=True)
class AuxEnergySensorEntityDescription(SensorEntityDescription):
    """Describe an AUX energy sensor and how to derive it from cloud history."""

    value_fn: Callable[[EnergyStatistics], float]


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


ENERGY_SENSORS = (
    AuxEnergySensorEntityDescription(
        key="energy_total",
        translation_key="energy_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda statistics: statistics.total_kwh,
    ),
    AuxEnergySensorEntityDescription(
        key="energy_today",
        translation_key="energy_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda statistics: statistics.energy_for_day(dt_util.now().date()),
    ),
)


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

    def energy_entities_for_device(device: AuxDevice) -> list[AuxEnergySensor]:
        return [
            AuxEnergySensor(coordinator, device["endpointId"], entity)
            for entity in ENERGY_SENSORS
        ]

    def has_energy_history(device: AuxDevice) -> bool:
        return coordinator.get_energy_statistics(device["endpointId"]) is not None

    setup_dynamic_entities(entry, coordinator, async_add_entities, entities_for_device)
    setup_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        energy_entities_for_device,
        device_ready=has_energy_history,
    )


class AuxCloudSensor(BaseEntity, SensorEntity):
    """Representation of an AUX Cloud temperature sensor."""

    entity_description: AuxSensorEntityDescription

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self._device)


class AuxEnergySensor(BaseEntity, SensorEntity):
    """Energy consumption reported by the AUX Cloud statistics service."""

    entity_description: AuxEnergySensorEntityDescription

    @property
    def available(self) -> bool:
        """Return whether the cloud still holds energy history for the device."""
        return (
            super().available
            and self.coordinator.get_energy_statistics(self._device_id) is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return the consumption derived from the cloud history."""
        statistics = self.coordinator.get_energy_statistics(self._device_id)
        if statistics is None:
            return None
        return self.entity_description.value_fn(statistics)
