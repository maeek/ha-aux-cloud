import logging
from homeassistant.const import Platform

_LOGGER = logging.getLogger(__package__)

DOMAIN = "aux_cloud"

DATA_AUX_CLOUD_CONFIG = "aux_cloud_config"
DATA_HASS_CONFIG = "aux_cloud_hass_config"
ATTR_CONFIG_ENTRY_ID = "entry_id"

# Configuration constants
CONF_FAMILIES = "families"
CONF_SELECTED_DEVICES = "selected_devices"

# Mode constants
MODE_OFF = 0
MODE_AUTO = 0
MODE_COOL = 1
MODE_HEAT = 4
MODE_DRY = 2
MODE_FAN_ONLY = 3

# Map AUX modes to Home Assistant HVAC modes
MODE_MAP = {
    MODE_OFF: "off",
    MODE_AUTO: "auto",
    MODE_COOL: "cool",
    MODE_HEAT: "heat",
    MODE_DRY: "dry",
    MODE_FAN_ONLY: "fan_only",
}

# Reverse map for setting HVAC modes
REVERSE_MODE_MAP = {v: k for k, v in MODE_MAP.items()}

# Fan mode constants
FAN_LOW = "low"
FAN_MEDIUM = "medium"
FAN_HIGH = "high"
FAN_TURBO = "turbo"
FAN_AUTO = "auto"

FAN_MODES = [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_TURBO, FAN_AUTO]

# Additional feature attributes
ATTR_ECO_MODE = "eco_mode"
ATTR_HEALTH_MODE = "health_mode"
ATTR_SLEEP_MODE = "sleep_mode"
ATTR_SELF_CLEAN = "self_clean"
ATTR_CHILD_LOCK = "child_lock"

# Brand information
MANUFACTURER = "AUX"

# Platforms to set up
PLATFORMS = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.WATER_HEATER,
]
