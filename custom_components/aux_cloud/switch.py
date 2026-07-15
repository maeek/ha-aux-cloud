"""Switch platform for AUX Cloud."""

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api.models import AuxDevice
from .coordinator import AuxCloudConfigEntry
from .devices import (
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
from .entity import BaseEntity, setup_dynamic_entities, supported_entity_descriptions

PARALLEL_UPDATES = 0

SWITCHES = (
    SwitchEntityDescription(
        key=AUX_ECOMODE,
        translation_key="aux_ecomode",
    ),
    SwitchEntityDescription(
        key=AC_POWER,
        translation_key="aux_ac_power",
    ),
    SwitchEntityDescription(
        key=HP_HEATER_POWER,
        translation_key="aux_hp_power",
    ),
    SwitchEntityDescription(
        key=HP_WATER_POWER,
        translation_key="aux_water_power",
    ),
    SwitchEntityDescription(
        key=HP_WATER_FAST_HOTWATER,
        translation_key="aux_fast_hotwater",
    ),
    SwitchEntityDescription(
        key=AC_AUXILIARY_HEAT,
        translation_key="aux_aux_heat",
    ),
    SwitchEntityDescription(
        key=AC_CLEAN,
        translation_key="aux_self_cleaning",
    ),
    SwitchEntityDescription(
        key=AC_CHILD_LOCK,
        translation_key="aux_child_lock",
    ),
    SwitchEntityDescription(
        key=AC_COMFORTABLE_WIND,
        translation_key="aux_comfortable_wind",
    ),
    SwitchEntityDescription(
        key=AC_HEALTH,
        translation_key="aux_health_mode",
    ),
    SwitchEntityDescription(
        key=AC_MILDEW_PROOF,
        translation_key="aux_mildew_proof",
    ),
    SwitchEntityDescription(
        key=AC_SLEEP,
        translation_key="aux_sleep_mode",
    ),
    SwitchEntityDescription(
        key=AC_SCREEN_DISPLAY,
        translation_key="aux_screen_display",
    ),
    SwitchEntityDescription(
        key=AC_POWER_LIMIT_SWITCH,
        translation_key="aux_power_limit",
    ),
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: AuxCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the AUX switch platform."""
    coordinator = entry.runtime_data

    def entities_for_device(device: AuxDevice) -> list[AuxSwitchEntity]:
        return [
            AuxSwitchEntity(
                coordinator,
                device["endpointId"],
                description,
            )
            for description in supported_entity_descriptions(device, SWITCHES)
        ]

    setup_dynamic_entities(entry, coordinator, async_add_entities, entities_for_device)


class AuxSwitchEntity(BaseEntity, SwitchEntity):
    """AUX Cloud switch entity."""

    @property
    def is_on(self) -> bool | None:
        """Return the state of the switch."""
        value = self._get_device_params().get(self.entity_description.key)
        return value == 1 if value is not None else None

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn the switch on."""
        await self._send_command(True)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn the switch off."""
        await self._send_command(False)

    async def _send_command(self, state: bool) -> None:
        """Send the command to the device."""
        await self._set_device_params({self.entity_description.key: int(state)})
