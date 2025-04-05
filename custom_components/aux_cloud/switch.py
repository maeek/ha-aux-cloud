from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.aux_cloud.api.const import (
    AC_AUXILIARY_HEAT,
    AC_CHILD_LOCK,
    AC_CLEAN,
    AC_COMFORTABLE_WIND,
    AC_HEALTH,
    AC_MILDEW_PROOF,
    AC_POWER,
    AC_SCREEN_DISPLAY,
    AC_SLEEP,
    AUX_ECOMODE,
    HP_HEATER_POWER,
    HP_WATER_FAST_HOTWATER,
    HP_WATER_POWER,
)
from custom_components.aux_cloud.util import BaseEntity

from .const import DOMAIN, _LOGGER

SWITCHES = {
    AUX_ECOMODE: {
        "description": SwitchEntityDescription(
            key=AUX_ECOMODE,
            name="Ecomode",
            icon="mdi:leaf",
            translation_key="aux_ecomode",
        ),
    },
    AC_POWER: {
        "description": SwitchEntityDescription(
            key=AC_POWER,
            name="AC Power",
            icon="mdi:air-conditioner",
            translation_key="aux_ac_power",
        ),
    },
    HP_HEATER_POWER: {
        "description": SwitchEntityDescription(
            key=HP_HEATER_POWER,
            name="Heat Pump Heater Power",
            icon="mdi:water-thermometer",
            translation_key="aux_hp_power",
        ),
    },
    HP_WATER_POWER: {
        "description": SwitchEntityDescription(
            key=HP_WATER_POWER,
            name="Water Heater Power",
            icon="mdi:water-boiler",
            translation_key="aux_water_power",
        ),
    },
    HP_WATER_FAST_HOTWATER: {
        "description": SwitchEntityDescription(
            key=HP_WATER_FAST_HOTWATER,
            name="Fast Hot Water",
            icon="mdi:water-boiler",
            translation_key="aux_fast_hotwater",
        ),
        "custom_mapping": {
            True: 9,
            False: 0,
        },
    },
    AC_AUXILIARY_HEAT: {
        "description": SwitchEntityDescription(
            key=AC_AUXILIARY_HEAT,
            name="Auxiliary Heat",
            icon="mdi:water-thermometer",
            translation_key="aux_aux_heat",
        ),
    },
    AC_CLEAN: {
        "description": SwitchEntityDescription(
            key=AC_CLEAN,
            name="Self Cleaning",
            icon="mdi:water-pump",
            translation_key="aux_self_cleaning",
        ),
    },
    AC_CHILD_LOCK: {
        "description": SwitchEntityDescription(
            key=AC_CHILD_LOCK,
            name="Child Lock",
            icon="mdi:lock",
            translation_key="aux_child_lock",
        ),
    },
    AC_COMFORTABLE_WIND: {
        "description": SwitchEntityDescription(
            key=AC_COMFORTABLE_WIND,
            name="Comfortable Wind",
            icon="mdi:fan",
            translation_key="aux_comfortable_wind",
        ),
    },
    AC_HEALTH: {
        "description": SwitchEntityDescription(
            key=AC_HEALTH,
            name="Health Mode",
            icon="mdi:shield-check",
            translation_key="aux_health_mode",
        ),
    },
    AC_MILDEW_PROOF: {
        "description": SwitchEntityDescription(
            key=AC_MILDEW_PROOF,
            name="Mildew Proof",
            icon="mdi:water-off",
            translation_key="aux_mildew_proof",
        ),
    },
    AC_SLEEP: {
        "description": SwitchEntityDescription(
            key=AC_SLEEP,
            name="Sleep Mode",
            icon="mdi:sleep",
            translation_key="aux_sleep_mode",
        ),
    },
    AC_SCREEN_DISPLAY: {
        "description": SwitchEntityDescription(
            key=AC_SCREEN_DISPLAY,
            name="Screen Display",
            icon="mdi:monitor-dashboard",
            translation_key="aux_screen_display",
        ),
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AUX switch platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities = []

    for device in coordinator.data["devices"]:
        if "params" in device:
            for switch in SWITCHES.values():
                if switch["description"].key in device["params"]:
                    entities.append(
                        AuxSwitchEntity(
                            coordinator, device["endpointId"], switch["description"]
                        )
                    )
                    _LOGGER.debug(
                        f"Adding switch entity for {device['friendlyName']} with option {switch['description'].key}"
                    )

    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.info("No AUX switch devices added")


class AuxSwitchEntity(BaseEntity, CoordinatorEntity, SwitchEntity):
    """AUX Cloud switch entity."""

    def __init__(self, coordinator, device_id, entity_description, custom_mapping=None):
        """Initialize the switch entity."""
        super().__init__(coordinator, device_id, entity_description)
        self._device_id = device_id
        self._option = self.entity_description.key
        self._custom_mapping = custom_mapping
        self.entity_id = f"switch.{self._attr_unique_id}"

    @property
    def is_on(self):
        """Return the state of the switch."""
        return self._get_device_params().get(self._option) == 1

    async def async_turn_on(self):
        """Turn the switch on."""
        await self._send_command(True)

    async def async_turn_off(self):
        """Turn the switch off."""
        await self._send_command(False)

    async def _send_command(self, state: bool):
        """Send the command to the device."""
        try:
            if self._custom_mapping:
                state = self._custom_mapping.get(state)

            await self._set_device_params({self._option: int(state)})
        except Exception as ex:
            _LOGGER.error(f"Failed to set switch state for {self._device_id}: {ex}")
