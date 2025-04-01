"""Climate platform for AUX Cloud integration."""

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    ClimateEntityDescription,
    HVACMode,
    HVACAction,
)
from homeassistant.components.climate.const import (
    FAN_AUTO,
    SWING_OFF,
    SWING_HORIZONTAL,
    SWING_VERTICAL,
    SWING_BOTH,
    PRESET_ECO,
    PRESET_NONE
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.aux_cloud.api.const import AUX_PRODUCT_CATEGORY, COOLING, HEATING, POWER_OFF, POWER_ON
from custom_components.aux_cloud.util import BaseEntity

from .const import DOMAIN, MODE_MAP, REVERSE_MODE_MAP, FAN_MODES, _LOGGER


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AUX climate platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities = []

    # Create climate entities for each device
    for device in coordinator.data["devices"]:
        if device.get("productId") in AUX_PRODUCT_CATEGORY.AC:
            entities.append(
              AuxACClimateEntity(
                coordinator,
                device['endpointId'],
                ClimateEntityDescription(
                  key="ac",
                  name="Air Conditioner",
                  translation_key="aux_ac",
                  icon="mdi:air-conditioner",
                  unit_of_measurement=UnitOfTemperature.CELSIUS,
                )
              )
            )
        elif device.get("productId") in AUX_PRODUCT_CATEGORY.HEAT_PUMP:
            entities.append(
              AuxHeatPumpClimateEntity(
                coordinator,
                device['endpointId'],
                ClimateEntityDescription(
                  key="heat_pump_central_heating",
                  name="Central Heating",
                  translation_key="aux_heater",
                  icon="mdi:hvac",
                  unit_of_measurement=UnitOfTemperature.CELSIUS,
                )
              )
            )

    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.info("No AUX climate devices added")


class AuxHeatPumpClimateEntity(BaseEntity, CoordinatorEntity, ClimateEntity):
    """AUX Cloud heat pump climate entity."""

    def __init__(self, coordinator, device_id, entity_description: ClimateEntityDescription):
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
        self._attr_temperature_unit = entity_description.unit_of_measurement
        self._attr_preset_modes = [PRESET_NONE, PRESET_ECO]

        icon = self.coordinator.api.url + self._get_device().get("icon")
        self._attr_entity_picture = icon if icon else None
        
    @property
    def preset_mode(self):
        """Return the current preset mode."""
        if self._get_device_params().get("ecomode", False):
            return PRESET_ECO
        return PRESET_NONE

    @property
    def target_temperature(self):
        """Return the target water temperature."""
        return self._get_device_params().get("ac_temp", None) / 10 if "ac_temp" in self._get_device_params() else None

    @property
    def hvac_mode(self):
        """Return the current operation mode."""
        if not self._get_device_params().get("ac_pwr", False):
            return HVACMode.OFF
        return HVACMode.HEAT

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new operation mode."""
        if hvac_mode == HVACMode.OFF:
            params = POWER_OFF
        elif hvac_mode == HVACMode.HEAT:
            params = { **HEATING, **POWER_ON }
        elif hvac_mode == HVACMode.COOL:
            params = { **COOLING, **POWER_ON }
        else:
            return

        await self._set_device_params(params)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self):
        """Turn the heat pump on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        """Turn the heat pump off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_mode(self, preset_mode: str):
        """Set the preset mode."""
        if preset_mode == PRESET_ECO:
            await self._set_device_params({"ecomode": 1 })
        else:
            await self._set_device_params({"ecomode": 0 })

        await self.coordinator.async_request_refresh()

class AuxACClimateEntity(BaseEntity, CoordinatorEntity, ClimateEntity):
    """AUX Cloud climate entity."""

    def __init__(self, coordinator, device_id, entity_description: ClimateEntityDescription):
        """Initialize the climate entity."""
        super().__init__(coordinator, device_id, entity_description)
        self._attr_temperature_unit = entity_description.unit_of_measurement
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        self._attr_hvac_modes = list(MODE_MAP.values())
        self._attr_fan_modes = FAN_MODES
        self._attr_swing_modes = [SWING_OFF, SWING_VERTICAL, SWING_HORIZONTAL, SWING_BOTH]
        self._attr_min_temp = 16
        self._attr_max_temp = 30
        self._attr_target_temperature_step = 0.5

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._get_device_params().get("envtemp", None) / 10 if "envtemp" in self._get_device_params() else None

    @property
    def target_temperature(self):
        """Return the target temperature."""
        return self._get_device_params().get("settemp", None) / 10 if "settemp" in self._get_device_params() else None

    @property
    def hvac_mode(self):
        """Return the current operation mode."""
        mode = self._get_device_params().get("ac_mode", None)
        if mode is None or not self._get_device_params().get("pwr", False):
            return HVACMode.OFF
        return MODE_MAP.get(mode, HVACMode.OFF)

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
        return self._get_device_params().get("fanspeed", FAN_AUTO)

    @property
    def swing_mode(self):
        """Return the swing mode."""
        horizontal = self._get_device_params().get("swing_horizontal", False)
        vertical = self._get_device_params().get("swing_vertical", False)

        if horizontal and vertical:
            return SWING_BOTH
        elif horizontal:
            return SWING_HORIZONTAL
        elif vertical:
            return SWING_VERTICAL
        else:
            return SWING_OFF

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return

        temperature = kwargs[ATTR_TEMPERATURE]
        if temperature < self._attr_min_temp:
            temperature = self._attr_min_temp
        elif temperature > self._attr_max_temp:
            temperature = self._attr_max_temp

        await self.coordinator.api.set_device_params(self.coordinator.get_device_by_endpoint_id(self._device_id), {"settemp": int(temperature * 10)})
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new operation mode."""
        if hvac_mode == HVACMode.OFF:
            params = {"power": False}
        else:
            aux_mode = REVERSE_MODE_MAP.get(hvac_mode)
            if aux_mode is None:
                return
            params = {"power": True, "mode": aux_mode}

        await self.coordinator.api.set_device_params(self.coordinator.get_device_by_endpoint_id(self._device_id), params)
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode):
        """Set new fan mode."""
        await self.coordinator.api.set_device_params(self.coordinator.get_device_by_endpoint_id(self._device_id), {"fanspeed": fan_mode})
        await self.coordinator.async_request_refresh()

    async def async_set_swing_mode(self, swing_mode):
        """Set new swing mode."""
        horizontal = swing_mode in [SWING_HORIZONTAL, SWING_BOTH]
        vertical = swing_mode in [SWING_VERTICAL, SWING_BOTH]

        params = {"swing_horizontal": horizontal, "swing_vertical": vertical}
        await self.coordinator.api.set_device_params(self.coordinator.get_device_by_endpoint_id(self._device_id), params)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self):
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self):
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
