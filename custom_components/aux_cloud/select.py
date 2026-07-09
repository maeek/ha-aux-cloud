"""Select platform for AUX Cloud integration."""

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .devices.profiles import (
    HP_HEATER_AUTO_WATER_TEMP,
    HP_QUIET_MODE,
    AuxProducts,
)
from .util import BaseEntity, setup_dynamic_entities

PARALLEL_UPDATES = 0

SELECTS = {
    HP_QUIET_MODE: {
        "description": SelectEntityDescription(
            key=HP_QUIET_MODE,
            name="Quiet Mode",
            icon="mdi:volume-mute",
            translation_key="aux_select_qtmode",
        ),
        "state_icons": {
            "off": {
                "value": 0,
                "icon": "mdi:volume-high",
            },
            "quiet_1": {
                "value": 1,
                "icon": "mdi:volume-off",
            },
            "quiet_2": {
                "value": 2,
                "icon": "mdi:volume-mute",
            },
        },
    },
    HP_HEATER_AUTO_WATER_TEMP: {
        "description": SelectEntityDescription(
            key=HP_HEATER_AUTO_WATER_TEMP,
            name="Auto Water Temperature",
            icon="mdi:water-thermometer",
            translation_key="aux_select_auto_water_temp",
        ),
        "state_icons": {
            "off": {
                "value": 0,
                "icon": "mdi:water-off",
            },
            "level_1": {
                "value": 1,
                "icon": "mdi:numeric-1",
            },
            "level_2": {
                "value": 2,
                "icon": "mdi:numeric-2",
            },
            "level_3": {
                "value": 3,
                "icon": "mdi:numeric-3",
            },
            "level_4": {
                "value": 4,
                "icon": "mdi:numeric-4",
            },
            "level_5": {
                "value": 5,
                "icon": "mdi:numeric-5",
            },
            "level_6": {
                "value": 6,
                "icon": "mdi:numeric-6",
            },
            "level_7": {
                "value": 7,
                "icon": "mdi:numeric-7",
            },
            "level_8": {
                "value": 8,
                "icon": "mdi:numeric-8",
            },
            "user_defined": {
                "value": 9,
                "icon": "mdi:account-cog",
            },
        },
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AUX select platform."""
    coordinator = entry.runtime_data.coordinator

    def entities_for_device(device):
        entities = []
        supported_params = AuxProducts.get_params_list(device["productId"])
        supported_special_params = AuxProducts.get_special_params_list(
            device["productId"]
        )

        for entity in SELECTS.values():
            if "productId" in device and (
                (supported_params and entity["description"].key in supported_params)
                or (
                    supported_special_params
                    and entity["description"].key in supported_special_params
                )
            ):
                entities.append(
                    AuxSelectEntity(
                        coordinator,
                        device["endpointId"],
                        entity_description=entity["description"],
                        options=entity["state_icons"],
                    )
                )
        return entities

    setup_dynamic_entities(entry, coordinator, async_add_entities, entities_for_device)


# pylint: disable=abstract-method
class AuxSelectEntity(BaseEntity, SelectEntity):
    """AUX Cloud select entity."""

    def __init__(
        self,
        coordinator,
        device_id,
        entity_description: SelectEntityDescription,
        options,
    ):
        super().__init__(coordinator, device_id, entity_description)
        self._options = options
        self._attr_options = list(options.keys())
        self._attr_current_option = self._get_device_params().get(
            self.entity_description.key, None
        )

    @property
    def current_option(self):
        options_reverse = {v["value"]: k for k, v in self._options.items()}
        return options_reverse.get(
            self._get_device_params().get(self.entity_description.key, None)
        )

    @property
    def icon(self):
        return self._options.get(self.current_option, {}).get("icon", None)

    async def async_select_option(self, option: str):
        if option not in self._attr_options:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_option",
                translation_placeholders={"option": option},
            )

        new_option = self._options[option]["value"]
        await self._set_device_params({self.entity_description.key: new_option})
