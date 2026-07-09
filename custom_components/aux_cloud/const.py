import logging

from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVACMode,
)
from homeassistant.const import Platform

from .devices.profiles import (
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
CONF_PHONE_NUMBER = "phone_number"
CONF_ACCOUNT_ID = "account_id"

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
FAN_MODE_HA_TO_AUX = {
    FAN_AUTO: ACFanSpeed.AUTO,
    FAN_LOW: ACFanSpeed.LOW,
    "medium_low": ACFanSpeed.MEDIUM_LOW,
    FAN_MEDIUM: ACFanSpeed.MEDIUM,
    "medium_high": ACFanSpeed.MEDIUM_HIGH,
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
    Platform.NUMBER,
]

MAX_FAILED_POLLS = 5

# The cloud relay is the normal state source. A slow authoritative inventory scan
# still runs so devices added or removed in the AUX app are reflected in HA.
TOPOLOGY_SCAN_INTERVAL_MINUTES = 30
DEVICE_QUERY_CONCURRENCY = 4
