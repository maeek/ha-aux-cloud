"""Fan platform for AUX Cloud integration."""

from homeassistant.components.climate.const import FAN_AUTO
from homeassistant.components.fan import (
    FanEntity,
    FanEntityDescription,
    FanEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .api.const import (
    AC_FAN_SPEED,
    AC_POWER,
    AC_POWER_OFF,
    AC_POWER_ON,
    ACFanSpeed,
    AuxProducts,
)
from .const import DOMAIN, FAN_MODE_AUX_TO_HA, FAN_MODE_HA_TO_AUX, _LOGGER
from .util import BaseEntity, get_ac_fan_modes


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AUX air conditioner fan entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []

    for device in coordinator.data["devices"]:
        if device.get("productId") not in AuxProducts.DeviceType.AC_GENERIC:
            continue
        fan_modes = get_ac_fan_modes(device)
        if any(mode != FAN_AUTO for mode in fan_modes):
            entities.append(
                AuxACFanEntity(
                    coordinator,
                    device["endpointId"],
                    FanEntityDescription(
                        key="fan",
                        name="Fan",
                        translation_key="aux_fan",
                        icon="mdi:fan",
                    ),
                    fan_modes,
                )
            )

    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.info("No AUX fan devices added")


# pylint: disable=abstract-method
class AuxACFanEntity(BaseEntity, CoordinatorEntity, FanEntity):
    """AUX Cloud air conditioner fan entity."""

    def __init__(
        self,
        coordinator,
        device_id,
        entity_description: FanEntityDescription,
        fan_modes: list[str],
    ):
        """Initialize the fan entity."""
        super().__init__(coordinator, device_id, entity_description)
        self._manual_fan_modes = [mode for mode in fan_modes if mode != FAN_AUTO]
        self._attr_speed_count = len(self._manual_fan_modes)
        self._attr_supported_features = (
            FanEntityFeature.SET_SPEED
            | FanEntityFeature.TURN_ON
            | FanEntityFeature.TURN_OFF
        )
        if FAN_AUTO in fan_modes:
            self._attr_preset_modes = [FAN_AUTO]
            self._attr_supported_features |= FanEntityFeature.PRESET_MODE
        self.entity_id = f"fan.{self._attr_unique_id}"

    @property
    def is_on(self):
        """Return whether the air conditioner is on."""
        return bool(self._get_device_params().get(AC_POWER, False))

    @property
    def percentage(self):
        """Return the current manual fan speed percentage."""
        if not self.is_on:
            return 0
        fan_mode = FAN_MODE_AUX_TO_HA.get(
            self._get_device_params().get(ACFanSpeed.PARAM_NAME)
        )
        if fan_mode not in self._manual_fan_modes:
            return None
        return ordered_list_item_to_percentage(self._manual_fan_modes, fan_mode)

    @property
    def preset_mode(self):
        """Return auto when automatic fan speed is active."""
        if (
            self.is_on
            and self._get_device_params().get(ACFanSpeed.PARAM_NAME)
            == FAN_MODE_HA_TO_AUX[FAN_AUTO]
        ):
            return FAN_AUTO
        return None

    async def async_set_percentage(self, percentage: int):
        """Set a manual fan speed percentage."""
        if percentage == 0:
            await self.async_turn_off()
            return
        fan_mode = percentage_to_ordered_list_item(self._manual_fan_modes, percentage)
        await self._set_device_params(
            {**AC_POWER_ON, AC_FAN_SPEED: FAN_MODE_HA_TO_AUX[fan_mode]}
        )

    async def async_set_preset_mode(self, preset_mode: str):
        """Set automatic fan speed."""
        await self._set_device_params(
            {**AC_POWER_ON, AC_FAN_SPEED: FAN_MODE_HA_TO_AUX[preset_mode]}
        )

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs,
    ):
        """Turn on the air conditioner fan."""
        if percentage is not None:
            await self.async_set_percentage(percentage)
        elif preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        else:
            await self._set_device_params(AC_POWER_ON)

    async def async_turn_off(self, **kwargs):
        """Turn off the air conditioner fan."""
        await self._set_device_params(AC_POWER_OFF)
