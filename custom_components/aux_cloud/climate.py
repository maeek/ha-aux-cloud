"""Climate platform for AUX Cloud integration."""

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.components.climate.const import (
    FAN_AUTO,
    SWING_OFF,
    SWING_HORIZONTAL,
    SWING_VERTICAL,
    SWING_BOTH,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from custom_components.aux_cloud.api.const import AUX_MODEL_TO_NAME

from .const import DOMAIN, MODE_HEAT, MODE_MAP, MODE_OFF, REVERSE_MODE_MAP, FAN_MODES, _LOGGER


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
        if device.get("productId") == "000000000000000000000000c0620000":
            # Only add climate entities for AUX devices
            entities.append(AuxACClimateEntity(coordinator, device['endpointId']))
        elif device.get("productId") == "000000000000000000000000c3aa0000":
            # Add heat pump entities for AUX heat pumps
            entities.append(AuxHeatPumpClimateEntity(coordinator, device['endpointId']))

    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.info("No AUX climate devices added")


class AuxHeatPumpClimateEntity(CoordinatorEntity, ClimateEntity):
    """AUX Cloud heat pump climate entity."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, device_id):
        """Initialize the heat pump climate entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_heat_pump"
        self._attr_name = f'{coordinator.get_device_by_endpoint_id(device_id).get("friendlyName")} Central Heating'
        self._attr_supported_features = (
          ClimateEntityFeature.TARGET_TEMPERATURE
          | ClimateEntityFeature.TURN_ON
          | ClimateEntityFeature.TURN_OFF
        )
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        self._attr_min_temp = 0  # Minimum temperature in Celsius
        self._attr_max_temp = 64  # Maximum temperature in Celsius
        self._attr_target_temperature_step = 1

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
          "identifiers": {(DOMAIN, self._device_id)},
          "connections": {(CONNECTION_NETWORK_MAC, self.coordinator.get_device_by_endpoint_id(self._device_id)["mac"])},
          "name": self._attr_name,
          "manufacturer": "AUX",
          "model": AUX_MODEL_TO_NAME[self.coordinator.get_device_by_endpoint_id(self._device_id)["productId"]] or "Unknown",
        }

    @property
    def target_temperature(self):
        """Return the target water temperature."""
        return self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("ac_temp", None) / 10 if "ac_temp" in self.coordinator.get_device_by_endpoint_id(self._device_id)["params"] else None

    @property
    def hvac_mode(self):
        """Return the current operation mode."""
        if not self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("ac_pwr", False):
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def eco_mode(self):
        """Return the current eco mode status."""
        return self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("eco_mode", False)

    async def async_set_temperature(self, **kwargs):
        """Set new target water temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return

        temperature = kwargs[ATTR_TEMPERATURE]
        if temperature < self._attr_min_temp:
            temperature = self._attr_min_temp
        elif temperature > self._attr_max_temp:
            temperature = self._attr_max_temp

        await self.coordinator.api.set_device_params(self.coordinator.get_device_by_endpoint_id(self._device_id), {"ac_temp": int(temperature * 10)})
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new operation mode."""
        if hvac_mode == HVACMode.OFF:
            params = {"ac_pwr": MODE_OFF}
        elif hvac_mode == HVACMode.HEAT:
            params = {
                "ac_mode": MODE_HEAT,
                "ac_pwr": 1,
            }
        else:
            return

        await self.coordinator.api.set_device_params(self.coordinator.get_device_by_endpoint_id(self._device_id), params)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self):
        """Turn the heat pump on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        """Turn the heat pump off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_eco_mode(self, eco_mode: bool):
        """Set eco mode on or off."""
        await self.coordinator.api.set_device_params(self.coordinator.get_device_by_endpoint_id(self._device_id), {"eco_mode": 1 if eco_mode else 0})
        await self.coordinator.async_request_refresh()


class AuxACClimateEntity(CoordinatorEntity, ClimateEntity):
    """AUX Cloud climate entity."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, device_id):
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}"
        self._attr_name = coordinator.get_device_by_endpoint_id(device_id).get("friendlyName", f"AUX {device_id}")
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
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "connections": {(CONNECTION_NETWORK_MAC, self.coordinator.get_device_by_endpoint_id(self._device_id)["mac"])},
            "name": self._attr_name,
            "manufacturer": "AUX",
            "model": self.coordinator.get_device_by_endpoint_id(self._device_id).get("productId", "Unknown"),
        }

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("envtemp", None) / 10 if "envtemp" in self.coordinator.get_device_by_endpoint_id(self._device_id)["params"] else None

    @property
    def target_temperature(self):
        """Return the target temperature."""
        return self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("settemp", None) / 10 if "settemp" in self.coordinator.get_device_by_endpoint_id(self._device_id)["params"] else None

    @property
    def hvac_mode(self):
        """Return the current operation mode."""
        mode = self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("mode", None)
        if mode is None or not self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("power", False):
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
        return self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("fanspeed", FAN_AUTO)

    @property
    def swing_mode(self):
        """Return the swing mode."""
        horizontal = self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("swing_horizontal", False)
        vertical = self.coordinator.get_device_by_endpoint_id(self._device_id)["params"].get("swing_vertical", False)

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
