"""Select platform for AUX Cloud integration."""

from collections.abc import Mapping
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api.models import AuxDevice
from .const import DOMAIN
from .coordinator import AuxCloudConfigEntry, AuxCloudCoordinator
from .devices import (
    HP_HEATER_AUTO_WATER_TEMP,
    HP_QUIET_MODE,
)
from .entity import BaseEntity, setup_dynamic_entities, supported_entity_descriptions

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class AuxSelectEntityDescription(SelectEntityDescription):
    """Describe the cloud value for each select option."""

    value_by_option: Mapping[str, int]


def _select_description(
    *,
    key: str,
    translation_key: str,
    options: tuple[tuple[str, int], ...],
) -> AuxSelectEntityDescription:
    """Build a typed select description from one compact option table."""
    return AuxSelectEntityDescription(
        key=key,
        translation_key=translation_key,
        value_by_option=dict(options),
    )


SELECTS = (
    _select_description(
        key=HP_QUIET_MODE,
        translation_key="aux_select_qtmode",
        options=(
            ("off", 0),
            ("quiet_1", 1),
            ("quiet_2", 2),
        ),
    ),
    _select_description(
        key=HP_HEATER_AUTO_WATER_TEMP,
        translation_key="aux_select_auto_water_temp",
        options=(
            ("off", 0),
            *((f"level_{level}", level) for level in range(1, 9)),
            ("user_defined", 9),
        ),
    ),
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: AuxCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the AUX select platform."""
    coordinator = entry.runtime_data

    def entities_for_device(device: AuxDevice) -> list[AuxSelectEntity]:
        return [
            AuxSelectEntity(
                coordinator,
                device["endpointId"],
                description,
            )
            for description in supported_entity_descriptions(device, SELECTS)
        ]

    setup_dynamic_entities(entry, coordinator, async_add_entities, entities_for_device)


class AuxSelectEntity(BaseEntity, SelectEntity):
    """AUX Cloud select entity."""

    def __init__(
        self,
        coordinator: AuxCloudCoordinator,
        device_id: str,
        entity_description: AuxSelectEntityDescription,
    ) -> None:
        super().__init__(coordinator, device_id, entity_description)
        self._option_by_value = {
            value: option
            for option, value in entity_description.value_by_option.items()
        }
        self._attr_options = list(entity_description.value_by_option)

    entity_description: AuxSelectEntityDescription

    @property
    def current_option(self) -> str | None:
        value = self._get_device_params().get(self.entity_description.key)
        return self._option_by_value.get(value) if isinstance(value, int) else None

    async def async_select_option(self, option: str) -> None:
        if option not in self._attr_options:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_option",
                translation_placeholders={"option": option},
            )

        new_option = self.entity_description.value_by_option[option]
        await self._set_device_params({self.entity_description.key: new_option})
