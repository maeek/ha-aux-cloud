import logging
from homeassistant.const import Platform
from homeassistant.components.climate import (
    HVACMode,
    FAN_MEDIUM,
    FAN_LOW,
    FAN_HIGH,
    FAN_AUTO,
)

from .api.const import (
    AC_MODE_AUTO,
    AC_MODE_COOLING,
    AC_MODE_DRY,
    AC_MODE_FAN,
    AC_MODE_HEATING,
    AUX_MODE,
    ACFanSpeed,
)

_LOGGER = logging.getLogger(__package__)

DOMAIN = "aux_cloud"

DATA_AUX_CLOUD_CONFIG = "aux_cloud_config"

# Configuration constants
CONF_FAMILIES = "families"
CONF_SELECTED_DEVICES = "selected_devices"

# Map AUX AC modes to Home Assistant HVAC modes
MODE_MAP_AUX_AC_TO_HA = {
    AC_MODE_AUTO.get(AUX_MODE): HVACMode.AUTO,
    AC_MODE_COOLING.get(AUX_MODE): HVACMode.COOL,
    AC_MODE_HEATING.get(AUX_MODE): HVACMode.HEAT,
    AC_MODE_DRY.get(AUX_MODE): HVACMode.DRY,
    AC_MODE_FAN.get(AUX_MODE): HVACMode.FAN_ONLY,
}

# Reverse map for setting HVAC modes
MODE_MAP_HA_TO_AUX = {v: k for k, v in MODE_MAP_AUX_AC_TO_HA.items()}

# Fan mode constants
FAN_MODE_SILENT = "silent"
FAN_MODE_MEDIUM_LOW = "medium-low"
FAN_MODE_MEDIUM_HIGH = "medium-high"
FAN_MODE_TURBO = "turbo"
FAN_MODE_HA_TO_AUX = {
    FAN_AUTO: ACFanSpeed.AUTO,
    FAN_MODE_SILENT: ACFanSpeed.MUTE,
    FAN_LOW: ACFanSpeed.LOW,
    FAN_MODE_MEDIUM_LOW: ACFanSpeed.MEDIUM_LOW,
    FAN_MEDIUM: ACFanSpeed.MEDIUM,
    FAN_MODE_MEDIUM_HIGH: ACFanSpeed.MEDIUM_HIGH,
    FAN_HIGH: ACFanSpeed.HIGH,
    FAN_MODE_TURBO: ACFanSpeed.TURBO,
}
FAN_MODE_AUX_TO_HA = {v: k for k, v in FAN_MODE_HA_TO_AUX.items()}
DEFAULT_AC_FAN_MODES = [
    FAN_AUTO,
    FAN_MODE_SILENT,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH,
    FAN_MODE_TURBO,
]

# Brand information
MANUFACTURER = "AUX"

# Platforms to set up
PLATFORMS = [
    Platform.CLIMATE,
    Platform.FAN,
    Platform.SENSOR,
    Platform.WATER_HEATER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.NUMBER,
]

MAX_FAILED_POLLS = 5
