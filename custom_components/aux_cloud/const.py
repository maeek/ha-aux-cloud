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
    Platform.NUMBER,
]

MAX_FAILED_POLLS = 5

# How long (in seconds) an optimistically-set parameter is protected from being
# overwritten by a stale/echoed value coming back from a cloud poll. The AUX
# cloud (and the physical device) can take a few seconds to actually apply a
# command and report the new state, so a poll that happens right after a
# "set" call can still return the old value. Without this grace period the
# UI would flicker/revert to the previous value even though the command was
# accepted (see https://github.com/maeek/ha-aux-cloud/issues/53).
OPTIMISTIC_GRACE_PERIOD_SECONDS = 15

# How long (in seconds) to wait after a temperature change before actually
# sending it to AUX Cloud. Rapid successive changes (dragging a slider,
# repeatedly tapping +/-) each cancel and replace the pending send, so only
# the final value is sent - avoiding a burst of overlapping API calls that
# can race with each other on the cloud/device side.
SET_TEMPERATURE_DEBOUNCE_SECONDS = 0.6
