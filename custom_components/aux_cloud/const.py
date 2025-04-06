import logging
from homeassistant.const import Platform
from homeassistant.components.climate import (
    HVACMode,
    FAN_MEDIUM,
    FAN_LOW,
    FAN_HIGH,
    FAN_AUTO,
)

from custom_components.aux_cloud.api.const import (
    AUX_MODE,
    AUX_MODE_AUTO,
    AUX_MODE_COOLING,
    AUX_MODE_DRY,
    AUX_MODE_FAN,
    AUX_MODE_HEATING,
    ACFanSpeed,
)

_LOGGER = logging.getLogger(__package__)

DOMAIN = "aux_cloud"

DATA_AUX_CLOUD_CONFIG = "aux_cloud_config"

# Configuration constants
CONF_FAMILIES = "families"
CONF_SELECTED_DEVICES = "selected_devices"

# Map AUX modes to Home Assistant HVAC modes
MODE_MAP_AUX_TO_HA = {
    AUX_MODE_AUTO.get(AUX_MODE): HVACMode.AUTO,
    AUX_MODE_COOLING.get(AUX_MODE): HVACMode.COOL,
    AUX_MODE_HEATING.get(AUX_MODE): HVACMode.HEAT,
    AUX_MODE_DRY.get(AUX_MODE): HVACMode.DRY,
    AUX_MODE_FAN.get(AUX_MODE): HVACMode.FAN_ONLY,
}

# Reverse map for setting HVAC modes
MODE_MAP_HA_TO_AUX = {v: k for k, v in MODE_MAP_AUX_TO_HA.items()}

# Fan mode constants
FAN_MODE_HA_TO_AUX = {
    FAN_AUTO: ACFanSpeed.AUTO,
    FAN_LOW: ACFanSpeed.LOW,
    FAN_MEDIUM: ACFanSpeed.MEDIUM,
    FAN_HIGH: ACFanSpeed.HIGH,
    "turbo": ACFanSpeed.TURBO,
    "silent": ACFanSpeed.MUTE,
}
FAN_MODE_AUX_TO_HA = {v: k for k, v in FAN_MODE_HA_TO_AUX.items()}

# Brand information
MANUFACTURER = "AUX"

# Platforms to set up
PLATFORMS = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.WATER_HEATER,
    Platform.SELECT,
    Platform.SWITCH,
]
