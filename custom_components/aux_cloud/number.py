from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.const import (
    AC_POWER_LIMIT,
    AUX_MODEL_PARAMS_LIST,
    AUX_MODEL_SPECIAL_PARAMS_LIST,
)
from .util import BaseEntity
from .const import DOMAIN, _LOGGER

NUMBERS = {
    AC_POWER_LIMIT: {
        "description": NumberEntityDescription(
            key=AC_POWER_LIMIT,
            name="Power Limit Percentage",
            icon="mdi:percent",
            translation_key="aux_power_limit_percentage",
        ),
        "min_value": 0,
        "max_value": 90,
        "step": 1,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AUX number platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities = []

    for device in coordinator.data["devices"]:
        for number in NUMBERS.values():
            if "productId" in device and (
                (
                    device["productId"] in AUX_MODEL_PARAMS_LIST
                    and number["description"].key
                    in AUX_MODEL_PARAMS_LIST.get(device["productId"])
                )
                or (
                    device["productId"] in AUX_MODEL_SPECIAL_PARAMS_LIST
                    and number["description"].key
                    in AUX_MODEL_SPECIAL_PARAMS_LIST.get(device["productId"])
                )
            ):
                entities.append(
                    AuxNumberEntity(
                        coordinator,
                        device["endpointId"],
                        number["description"],
                        number["min_value"],
                        number["max_value"],
                        number["step"],
                    )
                )
                _LOGGER.debug(
                    "Adding number entity for %s with option %s",
                    device["friendlyName"],
                    number["description"].key,
                )

    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.info("No AUX number devices added")


class AuxNumberEntity(BaseEntity, CoordinatorEntity, NumberEntity):
    """AUX Cloud number entity."""

    def __init__(
        self, coordinator, device_id, entity_description, min_value, max_value, step
    ):
        """Initialize the number entity."""
        super().__init__(coordinator, device_id, entity_description)
        self._device_id = device_id
        self._option = self.entity_description.key
        self._attr_min_value = min_value
        self._attr_max_value = max_value
        self._attr_step = step
        self.entity_id = f"number.{self._attr_unique_id}"

    @property
    def value(self):
        """Return the current value of the number."""
        return self._get_device_params().get(self._option, 0)

    async def async_set_value(self, value: float):
        """Set the value of the number."""
        try:
            await self._set_device_params({self._option: int(value)})
        except Exception as ex:
            _LOGGER.error("Failed to set number value for %s: %s", self._device_id, ex)
