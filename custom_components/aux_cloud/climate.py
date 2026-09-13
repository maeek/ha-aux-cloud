"""Climate platform for AUX Cloud integration."""

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
)
from homeassistant.components.climate.const import (
    PRESET_ECO,
    PRESET_NONE,
    SWING_BOTH,
    SWING_HORIZONTAL,
    SWING_OFF,
    SWING_VERTICAL,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api.models import AuxDevice
from .const import (
    FAN_MODE_AUX_TO_HA,
    FAN_MODE_HA_TO_AUX,
    MODE_MAP_AUX_AC_TO_HA,
    MODE_MAP_HA_TO_AUX,
)
from .coordinator import AuxCloudConfigEntry, AuxCloudCoordinator
from .devices import (
    AC_FAN_SPEED,
    AC_POWER,
    AC_POWER_OFF,
    AC_POWER_ON,
    AC_SWING_HORIZONTAL,
    AC_SWING_HORIZONTAL_OFF,
    AC_SWING_HORIZONTAL_ON,
    AC_SWING_VERTICAL,
    AC_SWING_VERTICAL_OFF,
    AC_SWING_VERTICAL_ON,
    AC_TEMPERATURE_AMBIENT,
    AC_TEMPERATURE_TARGET,
    AUX_ECOMODE_OFF,
    AUX_ECOMODE_ON,
    AUX_MODE,
    HP_HEATER_POWER,
    HP_HEATER_POWER_OFF,
    HP_HEATER_POWER_ON,
    HP_HEATER_TEMPERATURE_TARGET,
    HP_MODE_COOLING,
    HP_MODE_HEATING,
    DeviceType,
    ProductProfile,
    encode_ac_temperature_command,
    get_device_profile,
)
from .entity import BaseEntity, setup_dynamic_entities

PARALLEL_UPDATES = 0

AC_DESCRIPTION = ClimateEntityDescription(
    key="ac",
    translation_key="aux_ac",
)
HEAT_PUMP_DESCRIPTION = ClimateEntityDescription(
    key="heat_pump_central_heating",
    translation_key="aux_heater",
)
HVAC_ACTION_BY_MODE = {
    HVACMode.OFF: HVACAction.OFF,
    HVACMode.HEAT: HVACAction.HEATING,
    HVACMode.COOL: HVACAction.COOLING,
    HVACMode.DRY: HVACAction.DRYING,
    HVACMode.FAN_ONLY: HVACAction.FAN,
}


def _ac_hvac_modes(profile: ProductProfile) -> list[HVACMode]:
    """Return supported Home Assistant HVAC modes for a product profile."""
    return [
        HVACMode.OFF,
        *(
            MODE_MAP_AUX_AC_TO_HA[mode]
            for mode in profile.hvac_modes
            if mode in MODE_MAP_AUX_AC_TO_HA
        ),
    ]


def _ac_fan_modes(profile: ProductProfile) -> list[str]:
    """Return supported Home Assistant fan modes for a product profile."""
    return [
        FAN_MODE_AUX_TO_HA[speed]
        for speed in profile.fan_speeds
        if speed in FAN_MODE_AUX_TO_HA
    ]


def _ac_swing_modes(profile: ProductProfile) -> list[str]:
    """Return supported Home Assistant swing modes for a product profile."""
    modes = [SWING_OFF]
    if profile.vertical_swing:
        modes.append(SWING_VERTICAL)
    if profile.horizontal_swing:
        modes.append(SWING_HORIZONTAL)
    if profile.vertical_swing and profile.horizontal_swing:
        modes.append(SWING_BOTH)
    return modes


def _ac_supported_features(profile: ProductProfile) -> ClimateEntityFeature:
    """Return supported Home Assistant climate features for a profile."""
    features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    if profile.horizontal_swing or profile.vertical_swing:
        features |= ClimateEntityFeature.SWING_MODE
    return features


def _clamp_temperature(value: float, minimum: float, maximum: float) -> float:
    """Clamp a requested temperature to the entity's supported range."""
    return min(max(value, minimum), maximum)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: AuxCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the AUX climate platform."""
    coordinator = entry.runtime_data

    def entities_for_device(device: AuxDevice) -> list[ClimateEntity]:
        device_type = get_device_profile(device).device_type
        if device_type is DeviceType.AIR_CONDITIONER:
            return [
                AuxACClimateEntity(
                    coordinator,
                    device["endpointId"],
                    AC_DESCRIPTION,
                )
            ]
        if device_type is DeviceType.HEAT_PUMP:
            return [
                AuxHeatPumpClimateEntity(
                    coordinator,
                    device["endpointId"],
                    HEAT_PUMP_DESCRIPTION,
                )
            ]
        return []

    setup_dynamic_entities(entry, coordinator, async_add_entities, entities_for_device)


class AuxHeatPumpClimateEntity(BaseEntity, ClimateEntity):
    """AUX Cloud heat pump climate entity."""

    def __init__(
        self,
        coordinator: AuxCloudCoordinator,
        device_id: str,
        entity_description: ClimateEntityDescription,
    ) -> None:
        """Initialize the heat pump climate entity."""
        super().__init__(coordinator, device_id, entity_description)
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.PRESET_MODE
        )
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
        self._attr_min_temp = 0  # Minimum temperature in Celsius
        self._attr_max_temp = 64  # Maximum temperature in Celsius
        self._attr_target_temperature_step = 1
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_preset_modes = [PRESET_NONE, PRESET_ECO]

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        value = self._get_device_params().get("ecomode")
        if value is None:
            return None
        if value:
            return PRESET_ECO
        return PRESET_NONE

    @property
    def target_temperature(self) -> float | None:
        """Return the target water temperature."""
        value = self._get_device_params().get(HP_HEATER_TEMPERATURE_TARGET)
        return value / 10 if isinstance(value, (int, float)) else None

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current operation mode."""
        params = self._get_device_params()
        power = params.get(HP_HEATER_POWER)
        if power is None:
            return None
        if not power:
            return HVACMode.OFF
        mode = params.get(AUX_MODE)
        if mode == HP_MODE_COOLING:
            return HVACMode.COOL
        if mode == HP_MODE_HEATING:
            return HVACMode.HEAT
        return None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new operation mode."""
        if hvac_mode == HVACMode.OFF:
            params = HP_HEATER_POWER_OFF
        elif hvac_mode == HVACMode.HEAT:
            params = {AUX_MODE: HP_MODE_HEATING, **HP_HEATER_POWER_ON}
        elif hvac_mode == HVACMode.COOL:
            params = {AUX_MODE: HP_MODE_COOLING, **HP_HEATER_POWER_ON}
        else:
            return

        await self._set_device_params(params)

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action."""
        mode = self.hvac_mode
        return HVAC_ACTION_BY_MODE.get(mode) if mode is not None else None

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn the heat pump on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn the heat pump off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        if preset_mode == PRESET_ECO:
            await self._set_device_params(AUX_ECOMODE_ON)
        else:
            await self._set_device_params(AUX_ECOMODE_OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return

        temperature = kwargs[ATTR_TEMPERATURE]
        if not isinstance(temperature, (int, float)):
            return
        temperature = _clamp_temperature(
            temperature, self._attr_min_temp, self._attr_max_temp
        )

        await self._set_device_params(
            {HP_HEATER_TEMPERATURE_TARGET: int(temperature * 10)}
        )


class AuxACClimateEntity(BaseEntity, ClimateEntity):
    """AUX Cloud climate entity."""

    def __init__(
        self,
        coordinator: AuxCloudCoordinator,
        device_id: str,
        entity_description: ClimateEntityDescription,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, device_id, entity_description)
        self._profile = get_device_profile(self._device)
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_supported_features = _ac_supported_features(self._profile)
        self._attr_hvac_modes = _ac_hvac_modes(self._profile)
        self._attr_fan_modes = _ac_fan_modes(self._profile)
        self._attr_swing_modes = _ac_swing_modes(self._profile)
        self._attr_min_temp = 16
        self._attr_max_temp = 32
        self._attr_target_temperature_step = 0.5

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        value = self._get_device_params().get(AC_TEMPERATURE_AMBIENT)
        return value / 10 if isinstance(value, (int, float)) else None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        value = self._get_device_params().get(AC_TEMPERATURE_TARGET)
        return value / 10 if isinstance(value, (int, float)) else None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return

        temperature = kwargs[ATTR_TEMPERATURE]
        if not isinstance(temperature, (int, float)):
            return
        temperature = _clamp_temperature(
            temperature, self._attr_min_temp, self._attr_max_temp
        )
        await self._set_device_params(
            encode_ac_temperature_command(self._device, temperature)
        )

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current operation mode."""
        params = self._get_device_params()
        power = params.get(AC_POWER)
        if power is None:
            return None
        if not power:
            return HVACMode.OFF
        mode = params.get(AUX_MODE)
        return MODE_MAP_AUX_AC_TO_HA.get(mode) if isinstance(mode, int) else None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set a new operation mode."""
        if hvac_mode == HVACMode.OFF:
            params = AC_POWER_OFF
        else:
            aux_mode = MODE_MAP_HA_TO_AUX.get(hvac_mode)
            if aux_mode is None or aux_mode not in self._profile.hvac_modes:
                return
            params = {**AC_POWER_ON, AUX_MODE: aux_mode}

        await self._set_device_params(params)

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action."""
        mode = self.hvac_mode
        return HVAC_ACTION_BY_MODE.get(mode) if mode is not None else None

    @property
    def fan_mode(self) -> str | None:
        """Return the fan mode."""
        value = self._get_device_params().get(AC_FAN_SPEED)
        return FAN_MODE_AUX_TO_HA.get(value) if value is not None else None

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Async set new fan mode."""
        if fan_mode is None:
            return

        fan_speed = FAN_MODE_HA_TO_AUX.get(fan_mode)
        if fan_speed is None or fan_speed not in self._profile.fan_speeds:
            return

        await self._set_device_params({AC_FAN_SPEED: fan_speed})

    @property
    def swing_mode(self) -> str | None:
        """Return the swing mode."""
        params = self._get_device_params()
        supported_keys = {
            key
            for supported, key in (
                (self._profile.horizontal_swing, AC_SWING_HORIZONTAL),
                (self._profile.vertical_swing, AC_SWING_VERTICAL),
            )
            if supported
        }
        if supported_keys and supported_keys.isdisjoint(params):
            return None
        horizontal = self._profile.horizontal_swing and bool(
            params.get(AC_SWING_HORIZONTAL)
        )
        vertical = self._profile.vertical_swing and bool(params.get(AC_SWING_VERTICAL))

        return (
            SWING_BOTH
            if horizontal and vertical
            else (
                SWING_HORIZONTAL
                if horizontal
                else SWING_VERTICAL
                if vertical
                else SWING_OFF
            )
        )

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new swing mode."""
        params: dict[str, int] = {}
        if self._profile.vertical_swing:
            params.update(
                AC_SWING_VERTICAL_ON
                if swing_mode in [SWING_VERTICAL, SWING_BOTH]
                else AC_SWING_VERTICAL_OFF
            )
        if self._profile.horizontal_swing:
            params.update(
                AC_SWING_HORIZONTAL_ON
                if swing_mode in [SWING_HORIZONTAL, SWING_BOTH]
                else AC_SWING_HORIZONTAL_OFF
            )

        if params:
            await self._set_device_params(params)

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Async turn the entity on."""
        await self._set_device_params(AC_POWER_ON)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Async turn the entity off."""
        await self._set_device_params(AC_POWER_OFF)
