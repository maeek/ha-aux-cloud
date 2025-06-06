from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.const import AC_POWER_LIMIT, AuxProducts
from .const import _LOGGER, DOMAIN
from .util import BaseEntity

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
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities = []

    for device in coordinator.data["devices"]:
        supported_params = AuxProducts.get_params_list(device["productId"])
        supported_special_params = AuxProducts.get_special_params_list(
            device["productId"]
        )

        for entity in NUMBERS.values():
            if "productId" in device and (
                (supported_params and entity["description"].key in supported_params)
                or (
                    supported_special_params
                    and entity["description"].key in supported_special_params
                )
            ):
                entities.append(
                    AuxNumberEntity(
                        coordinator,
                        device["endpointId"],
                        entity["description"],
                    )
                )
                _LOGGER.debug(
                    "Adding number entity for %s with option %s",
                    device["friendlyName"],
                    entity["description"].key,
                )

    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.info("No AUX number devices added")


# pylint: disable=abstract-method
class AuxNumberEntity(BaseEntity, CoordinatorEntity, NumberEntity):
    """AUX Cloud number entity."""

    def __init__(self, coordinator, device_id, entity_description) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, device_id, entity_description)
        self._option = self.entity_description.key
        self.entity_id = f"number.{self._attr_unique_id}"

    @property
    def native_value(self):
        """Return the current native value of the number."""
        return self._get_device_params().get(self._option, 0)

    async def async_set_native_value(self, value: float):
        """Set the native value of the number."""
        try:
            await self._set_device_params({self._option: int(value)})
        except Exception as ex:
            _LOGGER.error("Failed to set number value for %s: %s", self._device_id, ex)
