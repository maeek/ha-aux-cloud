from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .devices.profiles import (
    AC_AUXILIARY_HEAT,
    AC_CHILD_LOCK,
    AC_CLEAN,
    AC_COMFORTABLE_WIND,
    AC_HEALTH,
    AC_MILDEW_PROOF,
    AC_POWER,
    AC_POWER_LIMIT_SWITCH,
    AC_SCREEN_DISPLAY,
    AC_SLEEP,
    AUX_ECOMODE,
    HP_HEATER_POWER,
    HP_WATER_FAST_HOTWATER,
    HP_WATER_POWER,
)
from .util import BaseEntity, setup_dynamic_entities, supported_entity_definitions

PARALLEL_UPDATES = 0

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
    },
    AC_AUXILIARY_HEAT: {
        "description": SwitchEntityDescription(
            key=AC_AUXILIARY_HEAT,
            name="Auxiliary Heat",
            icon="mdi:heat-wave",
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
    AC_POWER_LIMIT_SWITCH: {
        "description": SwitchEntityDescription(
            key=AC_POWER_LIMIT_SWITCH,
            name="Power Limit",
            icon="mdi:power-socket-eu",
            translation_key="aux_power_limit",
        ),
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AUX switch platform."""
    coordinator = entry.runtime_data.coordinator

    def entities_for_device(device):
        return [
            AuxSwitchEntity(
                coordinator,
                device["endpointId"],
                entity["description"],
                entity.get("custom_mapping"),
            )
            for entity in supported_entity_definitions(device, SWITCHES.values())
        ]

    setup_dynamic_entities(entry, coordinator, async_add_entities, entities_for_device)


# pylint: disable=abstract-method
class AuxSwitchEntity(BaseEntity, SwitchEntity):
    """AUX Cloud switch entity."""

    def __init__(self, coordinator, device_id, entity_description, custom_mapping=None):
        """Initialize the switch entity."""
        super().__init__(coordinator, device_id, entity_description)
        self._device_id = device_id
        self._option = self.entity_description.key
        self._custom_mapping = custom_mapping

    @property
    def is_on(self):
        """Return the state of the switch."""
        if self._custom_mapping:
            # If a custom mapping is provided, use it to determine the state
            return self._custom_mapping.get(True) == self._get_device_params().get(
                self._option
            )

        return self._get_device_params().get(self._option) == 1

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self._send_command(True)

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._send_command(False)

    async def _send_command(self, state: bool):
        """Send the command to the device."""
        if self._custom_mapping:
            state = self._custom_mapping.get(state)
        await self._set_device_params({self._option: int(state)})
