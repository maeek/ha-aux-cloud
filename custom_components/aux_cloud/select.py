"""Select platform for AUX Cloud integration."""

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.const import (
    AuxProducts,
    HP_HEATER_AUTO_WATER_TEMP,
    HP_QUIET_MODE,
)
from .const import DOMAIN, _LOGGER
from .util import BaseEntity

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
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities = []

    # Create select entities for each device
    for device in coordinator.data["devices"]:
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
                _LOGGER.debug(
                    "Adding select entity for %s with option %s",
                    device["friendlyName"],
                    entity["description"].key,
                )
    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.info("No AUX select devices added")


# pylint: disable=abstract-method
class AuxSelectEntity(BaseEntity, CoordinatorEntity, SelectEntity):
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
        self.entity_id = f"select.{self._attr_unique_id}"

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
        new_option = self._options.get(option).get("value", None)
        if option not in self._attr_options:
            _LOGGER.error("Invalid option selected: %s=%s", option, new_option)
            return

        await self._set_device_params({self.entity_description.key: new_option})
        await self.coordinator.async_request_refresh()
