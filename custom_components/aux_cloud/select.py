"""Select platform for AUX Cloud integration."""

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.const import (
    AUX_MODEL_PARAMS_LIST,
    AUX_MODEL_SPECIAL_PARAMS_LIST,
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
    }
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
        for entity in SELECTS.values():
            if "productId" in device and (
                (
                    device["productId"] in AUX_MODEL_PARAMS_LIST
                    and entity["description"].key
                    in AUX_MODEL_PARAMS_LIST.get(device["productId"])
                )
                or (
                    device["productId"] in AUX_MODEL_SPECIAL_PARAMS_LIST
                    and entity["description"].key
                    in AUX_MODEL_SPECIAL_PARAMS_LIST.get(device["productId"])
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
