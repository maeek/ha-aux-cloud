"""Constants shared by the AUX Cloud integration."""

from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVACMode,
)
from homeassistant.const import Platform

from .devices import (
    AC_FAN_AUTO,
    AC_FAN_HIGH,
    AC_FAN_LOW,
    AC_FAN_MEDIUM,
    AC_FAN_MEDIUM_HIGH,
    AC_FAN_MEDIUM_LOW,
    AC_FAN_MUTE,
    AC_FAN_TURBO,
    AC_MODE_AUTO,
    AC_MODE_COOLING,
    AC_MODE_DRY,
    AC_MODE_FAN,
    AC_MODE_HEATING,
)

DOMAIN = "aux_cloud"


# Configuration constants
CONF_FAMILIES = "families"
CONF_SELECTED_DEVICES = "selected_devices"
CONF_PHONE_NUMBER = "phone_number"
CONF_ACCOUNT_ID = "account_id"

# Map AUX AC modes to Home Assistant HVAC modes
MODE_MAP_AUX_AC_TO_HA = {
    AC_MODE_AUTO: HVACMode.AUTO,
    AC_MODE_COOLING: HVACMode.COOL,
    AC_MODE_HEATING: HVACMode.HEAT,
    AC_MODE_DRY: HVACMode.DRY,
    AC_MODE_FAN: HVACMode.FAN_ONLY,
}

# Reverse map for setting HVAC modes
MODE_MAP_HA_TO_AUX = {v: k for k, v in MODE_MAP_AUX_AC_TO_HA.items()}

# Fan mode constants
FAN_MODE_HA_TO_AUX = {
    FAN_AUTO: AC_FAN_AUTO,
    FAN_LOW: AC_FAN_LOW,
    "medium_low": AC_FAN_MEDIUM_LOW,
    FAN_MEDIUM: AC_FAN_MEDIUM,
    "medium_high": AC_FAN_MEDIUM_HIGH,
    FAN_HIGH: AC_FAN_HIGH,
    "turbo": AC_FAN_TURBO,
    "silent": AC_FAN_MUTE,
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
