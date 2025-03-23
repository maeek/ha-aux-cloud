"""Climate platform for AUX Cloud integration."""
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    SWING_OFF,
    SWING_HORIZONTAL,
    SWING_VERTICAL,
    SWING_BOTH,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .api.const import (
    DOMAIN,
    MODE_AUTO,
    MODE_COOL,
    MODE_HEAT,
    MODE_DRY,
    MODE_FAN_ONLY,
    MODE_OFF,
)

_LOGGER = logging.getLogger(__name__)

# Map AUX modes to Home Assistant modes
MODE_MAP = {
    MODE_AUTO: HVACMode.AUTO,
    MODE_COOL: HVACMode.COOL,
    MODE_HEAT: HVACMode.HEAT,
    MODE_DRY: HVACMode.DRY,
    MODE_FAN_ONLY: HVACMode.FAN_ONLY,
    MODE_OFF: HVACMode.OFF,
}

# Map Home Assistant modes to AUX modes
REVERSE_MODE_MAP = {v: k for k, v in MODE_MAP.items()}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AUX climate platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]

    entities = []

    # Create climate entities for each device
    for device in api.devices:
        entities.append(AuxClimateEntity(coordinator, api, device))

    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.info("No AUX climate devices added")

class AuxClimateEntity(CoordinatorEntity, ClimateEntity):
    """AUX Cloud climate entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, api, device):
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self.api = api
        self.device_id = device["id"]
        self.device_info = device

        # Set entity unique ID
        self._attr_unique_id = f"{DOMAIN}_{self.device_id}"

        # Set device name
        self._attr_name = device.get("name", f"AUX {self.device_id}")

        # Set supported features
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE |
            ClimateEntityFeature.FAN_MODE |
            ClimateEntityFeature.SWING_MODE |
            ClimateEntityFeature.TURN_ON |
            ClimateEntityFeature.TURN_OFF
        )

        # Set available modes
        self._attr_hvac_modes = [
            HVACMode.AUTO,
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
            HVACMode.OFF,
        ]

        # Set available fan modes
        self._attr_fan_modes = [
            FAN_AUTO,
            FAN_LOW,
            FAN_MEDIUM,
            FAN_HIGH,
        ]

        # Set available swing modes
        self._attr_swing_modes = [
            SWING_OFF,
            SWING_VERTICAL,
            SWING_HORIZONTAL,
            SWING_BOTH,
        ]

        # Set temperature range
        self._attr_min_temp = 16
        self._attr_max_temp = 30
        self._attr_target_temperature_step = 1

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self.device_id)},
            "name": self._attr_name,
            "manufacturer": "AUX",
            "model": self.device_info.get("model", "Unknown"),
            "sw_version": self.device_info.get("firmware_version", "Unknown"),
        }

    @property
    def current_temperature(self):
        """Return the current temperature."""
        status = self.get_device_status()
        if status and "current_temperature" in status:
            return status["current_temperature"]
        return None

    @property
    def target_temperature(self):
        """Return the target temperature."""
        status = self.get_device_status()
        if status and "target_temperature" in status:
            return status["target_temperature"]
        return None

    @property
    def hvac_mode(self):
        """Return the current operation mode."""
        status = self.get_device_status()
        if not status:
            return HVACMode.OFF

        if "power" in status and not status["power"]:
            return HVACMode.OFF

        if "mode" in status:
            return MODE_MAP.get(status["mode"], HVACMode.OFF)

        return HVACMode.OFF

    @property
    def hvac_action(self):
        """Return the current HVAC action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        status = self.get_device_status()
        if not status:
            return HVACAction.IDLE

        # Determine the current action based on status
        # This depends on the actual API response structure
        if "is_heating" in status and status["is_heating"]:
            return HVACAction.HEATING
        if "is_cooling" in status and status["is_cooling"]:
            return HVACAction.COOLING
        if "is_drying" in status and status["is_drying"]:
            return HVACAction.DRYING
        if "is_fan_only" in status and status["is_fan_only"]:
            return HVACAction.FAN

        return HVACAction.IDLE

    @property
    def fan_mode(self):
        """Return the fan mode."""
        status = self.get_device_status()
        if status and "fan_mode" in status:
            fan_mode = status["fan_mode"].lower()
            if fan_mode == "low":
                return FAN_LOW
            elif fan_mode == "medium":
                return FAN_MEDIUM
            elif fan_mode == "high":
                return FAN_HIGH
            else:
                return FAN_AUTO
        return FAN_AUTO

    @property
    def swing_mode(self):
        """Return the swing mode."""
        status = self.get_device_status()
        if not status:
            return SWING_OFF

        horizontal = status.get("swing_horizontal", False)
        vertical = status.get("swing_vertical", False)

        if horizontal and vertical:
            return SWING_BOTH
        elif horizontal:
            return SWING_HORIZONTAL
        elif vertical:
            return SWING_VERTICAL
        else:
            return SWING_OFF

    def get_device_status(self):
        """Get the latest status of the device."""
        for device in self.coordinator.data.devices:
            if device["id"] == self.device_id:
                # Return the device status if available in the coordinator data
                return device.get("status", {})

        # If not found in coordinator data, fetch it directly
        return self.api.get_device_status(self.device_id)

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return

        temperature = kwargs[ATTR_TEMPERATURE]

        # Ensure the temperature is within the valid range
        if temperature < self.min_temp:
            temperature = self.min_temp
        elif temperature > self.max_temp:
            temperature = self.max_temp

        state = {"target_temperature": temperature}

        await self.hass.async_add_executor_job(
            self.api.set_device_state, self.device_id, state
        )

        # Trigger an update
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new operation mode."""
        if hvac_mode == HVACMode.OFF:
            state = {"power": False}
        else:
            aux_mode = REVERSE_MODE_MAP.get(hvac_mode)
            if not aux_mode:
                return

            state = {
                "power": True,
                "mode": aux_mode,
            }

        await self.hass.async_add_executor_job(
            self.api.set_device_state, self.device_id, state
        )

        # Trigger an update
        await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode):
        """Set new fan mode."""
        aux_fan_mode = fan_mode.lower()

        state = {"fan_mode": aux_fan_mode}

        await self.hass.async_add_executor_job(
            self.api.set_device_state, self.device_id, state
        )

        # Trigger an update
        await self.coordinator.async_request_refresh()

    async def async_set_swing_mode(self, swing_mode):
        """Set new swing mode."""
        horizontal = False
        vertical = False

        if swing_mode == SWING_BOTH:
            horizontal = True
            vertical = True
        elif swing_mode == SWING_HORIZONTAL:
            horizontal = True
        elif swing_mode == SWING_VERTICAL:
            vertical = True

        state = {
            "swing_horizontal": horizontal,
            "swing_vertical": vertical,
        }

        await self.hass.async_add_executor_job(
            self.api.set_device_state, self.device_id, state
        )

        # Trigger an update
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self):
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self):
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)