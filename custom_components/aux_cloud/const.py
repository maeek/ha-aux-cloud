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

# Fan mode constants
FAN_LOW = "low"
FAN_MEDIUM = "medium"
FAN_HIGH = "high"
FAN_TURBO = "turbo"

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
    # Platform.BINARY_SENSOR,
    # Platform.CLIMATE,
    # Platform.SWITCH,
    # Platform.NUMBER,
    # Platform.WATER_HEATER,
    # Platform.FAN,
    Platform.SENSOR
]
