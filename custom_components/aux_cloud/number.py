from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .devices.profiles import AC_POWER_LIMIT
from .util import BaseEntity, setup_dynamic_entities, supported_entity_definitions

PARALLEL_UPDATES = 0

NUMBERS = {
    AC_POWER_LIMIT: {
        "description": NumberEntityDescription(
            key=AC_POWER_LIMIT,
            name="Power Limit Percentage",
            icon="mdi:percent",
            native_max_value=90,
            native_min_value=0,
            native_step=1,
            native_unit_of_measurement="%",
            translation_key="aux_power_limit_percentage",
        )
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AUX number platform."""
    coordinator = entry.runtime_data.coordinator

    def entities_for_device(device):
        return [
            AuxNumberEntity(
                coordinator,
                device["endpointId"],
                entity["description"],
            )
            for entity in supported_entity_definitions(device, NUMBERS.values())
        ]

    setup_dynamic_entities(entry, coordinator, async_add_entities, entities_for_device)


# pylint: disable=abstract-method
class AuxNumberEntity(BaseEntity, NumberEntity):
    """AUX Cloud number entity."""

    def __init__(self, coordinator, device_id, entity_description) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, device_id, entity_description)
        self._option = self.entity_description.key

    @property
    def native_value(self):
        """Return the current native value of the number."""
        return self._get_device_params().get(self._option, 0)

    async def async_set_native_value(self, value: float):
        """Set the native value of the number."""
        await self._set_device_params({self._option: int(value)})
