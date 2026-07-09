"""Climate platform for AUX Cloud integration."""

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import (
    FAN_AUTO,
    PRESET_ECO,
    PRESET_NONE,
    SWING_BOTH,
    SWING_HORIZONTAL,
    SWING_OFF,
    SWING_VERTICAL,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    _LOGGER,
    FAN_MODE_AUX_TO_HA,
    FAN_MODE_HA_TO_AUX,
    MODE_MAP_AUX_AC_TO_HA,
    MODE_MAP_HA_TO_AUX,
)
from .devices.profiles import (
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
    ACFanSpeed,
    AuxProducts,
    encode_ac_temperature_command,
    get_product_profile,
)
from .util import BaseEntity, setup_dynamic_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AUX climate platform."""
    coordinator = entry.runtime_data.coordinator

    def entities_for_device(device):
        if device.get("productId") in AuxProducts.DeviceType.AC_GENERIC:
            return [
                AuxACClimateEntity(
                    coordinator,
                    device["endpointId"],
                    ClimateEntityDescription(
                        key="ac",
                        name="Air Conditioner",
                        translation_key="aux_ac",
                        icon="mdi:air-conditioner",
                    ),
                )
            ]
        elif device.get("productId") in AuxProducts.DeviceType.HEAT_PUMP:
            return [
                AuxHeatPumpClimateEntity(
                    coordinator,
                    device["endpointId"],
                    ClimateEntityDescription(
                        key="heat_pump_central_heating",
                        name="Central Heating",
                        translation_key="aux_heater",
                        icon="mdi:hvac",
                    ),
                )
            ]
        return []

    setup_dynamic_entities(entry, coordinator, async_add_entities, entities_for_device)


# pylint: disable=abstract-method
class AuxHeatPumpClimateEntity(BaseEntity, ClimateEntity):
    """AUX Cloud heat pump climate entity."""

    def __init__(
        self, coordinator, device_id, entity_description: ClimateEntityDescription
    ):
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
    def preset_mode(self):
        """Return the current preset mode."""
        if self._get_device_params().get("ecomode", False):
            return PRESET_ECO
        return PRESET_NONE

    @property
    def target_temperature(self):
        """Return the target water temperature."""
        value = self._get_device_params().get(HP_HEATER_TEMPERATURE_TARGET)
        return value / 10 if isinstance(value, (int, float)) else None

    @property
    def hvac_mode(self):
        """Return the current operation mode."""
        if not self._get_device_params().get(HP_HEATER_POWER, False):
            return HVACMode.OFF
        if self._get_device_params().get(AUX_MODE) == HP_MODE_COOLING[AUX_MODE]:
            return HVACMode.COOL
        return HVACMode.HEAT

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new operation mode."""
        if hvac_mode == HVACMode.OFF:
            params = HP_HEATER_POWER_OFF
        elif hvac_mode == HVACMode.HEAT:
            params = {**HP_MODE_HEATING, **HP_HEATER_POWER_ON}
        elif hvac_mode == HVACMode.COOL:
            params = {**HP_MODE_COOLING, **HP_HEATER_POWER_ON}
        else:
            return

        await self._set_device_params(params)

    @property
    def hvac_action(self):
        """Return the current HVAC action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self.hvac_mode == HVACMode.HEAT:
            return HVACAction.HEATING
        if self.hvac_mode == HVACMode.COOL:
            return HVACAction.COOLING
        if self.hvac_mode == HVACMode.DRY:
            return HVACAction.DRYING
        if self.hvac_mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN

        return HVACAction.IDLE

    async def async_turn_on(self):
        """Turn the heat pump on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        """Turn the heat pump off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_mode(self, preset_mode: str):
        """Set the preset mode."""
        if preset_mode == PRESET_ECO:
            await self._set_device_params(AUX_ECOMODE_ON)
        else:
            await self._set_device_params(AUX_ECOMODE_OFF)

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return

        temperature = kwargs[ATTR_TEMPERATURE]
        if temperature < self._attr_min_temp:
            temperature = self._attr_min_temp
        elif temperature > self._attr_max_temp:
            temperature = self._attr_max_temp

        await self._set_device_params(
            {HP_HEATER_TEMPERATURE_TARGET: int(temperature * 10)}
        )

    async def async_set_fan_mode(self, fan_mode):
        """Set new fan mode."""
        _LOGGER.warning("Fan mode setting is not supported for heat pump devices")
        return


class AuxACClimateEntity(BaseEntity, ClimateEntity):
    """AUX Cloud climate entity."""

    def __init__(
        self, coordinator, device_id, entity_description: ClimateEntityDescription
    ):
        """Initialize the climate entity."""
        super().__init__(coordinator, device_id, entity_description)
        self._profile = get_product_profile(self._device.get("productId"))
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if self._profile.horizontal_swing or self._profile.vertical_swing:
            supported_features |= ClimateEntityFeature.SWING_MODE
        self._attr_supported_features = supported_features
        self._attr_hvac_modes = [
            HVACMode.OFF,
            *[
                MODE_MAP_AUX_AC_TO_HA[mode]
                for mode in self._profile.hvac_modes
                if mode in MODE_MAP_AUX_AC_TO_HA
            ],
        ]
        self._attr_fan_modes = [
            FAN_MODE_AUX_TO_HA[speed]
            for speed in self._profile.fan_speeds
            if speed in FAN_MODE_AUX_TO_HA
        ]
        swing_modes = [SWING_OFF]
        if self._profile.vertical_swing:
            swing_modes.append(SWING_VERTICAL)
        if self._profile.horizontal_swing:
            swing_modes.append(SWING_HORIZONTAL)
        if self._profile.vertical_swing and self._profile.horizontal_swing:
            swing_modes.append(SWING_BOTH)
        self._attr_swing_modes = swing_modes
        self._attr_min_temp = 16
        self._attr_max_temp = 32
        self._attr_target_temperature_step = 0.5

    @property
    def current_temperature(self):
        """Return the current temperature."""
        value = self._get_device_params().get(AC_TEMPERATURE_AMBIENT)
        return value / 10 if isinstance(value, (int, float)) else None

    @property
    def target_temperature(self):
        """Return the target temperature."""
        value = self._get_device_params().get(AC_TEMPERATURE_TARGET)
        return value / 10 if isinstance(value, (int, float)) else None

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return

        temperature = kwargs[ATTR_TEMPERATURE]
        if temperature < self._attr_min_temp:
            temperature = self._attr_min_temp
        elif temperature > self._attr_max_temp:
            temperature = self._attr_max_temp

        command_device = {
            **self._device,
            "params": self._get_device_params(),
        }
        await self._set_device_params(
            encode_ac_temperature_command(command_device, temperature)
        )

    @property
    def hvac_mode(self):
        """Return the current operation mode."""
        mode = self._get_device_params().get(AUX_MODE, None)
        if mode is None or not self._get_device_params().get(AC_POWER, False):
            return HVACMode.OFF
        return MODE_MAP_AUX_AC_TO_HA.get(mode, HVACMode.OFF)

    async def async_set_hvac_mode(self, hvac_mode):
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
    def hvac_action(self):
        """Return the current HVAC action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self.hvac_mode == HVACMode.HEAT:
            return HVACAction.HEATING
        if self.hvac_mode == HVACMode.COOL:
            return HVACAction.COOLING
        if self.hvac_mode == HVACMode.DRY:
            return HVACAction.DRYING
        if self.hvac_mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN

        return HVACAction.IDLE

    @property
    def fan_mode(self):
        """Return the fan mode."""
        value = self._get_device_params().get(ACFanSpeed.PARAM_NAME)
        return (
            FAN_MODE_AUX_TO_HA.get(value, FAN_AUTO) if value is not None else FAN_AUTO
        )

    async def async_set_fan_mode(self, fan_mode):
        """Async set new fan mode."""
        if fan_mode is None:
            return

        fan_speed = FAN_MODE_HA_TO_AUX.get(fan_mode)
        if fan_speed is None or fan_speed not in self._profile.fan_speeds:
            return

        await self._set_device_params({AC_FAN_SPEED: fan_speed})

    @property
    def swing_mode(self):
        """Return the swing mode."""
        horizontal = self._profile.horizontal_swing and bool(
            self._get_device_params().get(AC_SWING_HORIZONTAL, 0)
        )
        vertical = self._profile.vertical_swing and bool(
            self._get_device_params().get(AC_SWING_VERTICAL, 0)
        )

        return (
            SWING_BOTH
            if horizontal and vertical
            else (
                SWING_HORIZONTAL
                if horizontal
                else SWING_VERTICAL if vertical else SWING_OFF
            )
        )

    async def async_set_swing_mode(self, swing_mode):
        """Set new swing mode."""
        params = {}
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

    async def async_turn_on(self):
        """Async turn the entity on."""
        await self._set_device_params(AC_POWER_ON)

    async def async_turn_off(self):
        """Async turn the entity off."""
        await self._set_device_params(AC_POWER_OFF)
