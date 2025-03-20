import logging
from homeassistant.const import Platform

_LOGGER = logging.getLogger(__package__)

DOMAIN = "aux_cloud"

DATA_AUX_CLOUD_CONFIG = "aux_cloud_config"
DATA_HASS_CONFIG = "aux_cloud_hass_config"
ATTR_CONFIG_ENTRY_ID = "entry_id"

MANUFACTURER = "AUX"

PLATFORMS = [
    # Platform.BINARY_SENSOR,
    # Platform.CLIMATE,
    # Platform.SWITCH,
    # Platform.NUMBER,
    # Platform.WATER_HEATER,
    # Platform.FAN,
    Platform.SENSOR
]
