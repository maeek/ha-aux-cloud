"""Number platform for AUX Cloud."""

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api.models import AuxDevice
from .coordinator import AuxCloudConfigEntry
from .devices import AC_POWER_LIMIT
from .entity import BaseEntity, setup_dynamic_entities, supported_entity_descriptions

PARALLEL_UPDATES = 0

POWER_LIMIT_DESCRIPTION = NumberEntityDescription(
    key=AC_POWER_LIMIT,
    native_max_value=90,
    native_min_value=0,
    native_step=1,
    native_unit_of_measurement="%",
    translation_key="aux_power_limit_percentage",
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: AuxCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the AUX number platform."""
    coordinator = entry.runtime_data

    def entities_for_device(device: AuxDevice) -> list[AuxNumberEntity]:
        return [
            AuxNumberEntity(
                coordinator,
                device["endpointId"],
                entity,
            )
            for entity in supported_entity_descriptions(
                device, (POWER_LIMIT_DESCRIPTION,)
            )
        ]

    setup_dynamic_entities(entry, coordinator, async_add_entities, entities_for_device)


class AuxNumberEntity(BaseEntity, NumberEntity):
    """AUX Cloud number entity."""

    @property
    def native_value(self) -> float | int | None:
        """Return the current native value of the number."""
        value = self._get_device_params().get(self.entity_description.key)
        return value if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the native value of the number."""
        await self._set_device_params({self.entity_description.key: int(value)})
