from datetime import timedelta
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import Throttle

from .const import (
    _LOGGER,
    DOMAIN,
    DATA_AUX_CLOUD_CONFIG,
    DATA_HASS_CONFIG,
    PLATFORMS
)

from .api.aux_cloud import AuxCloudAPI

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=180)

# Updated schema to include both email and password
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema({
            vol.Required(CONF_EMAIL): cv.string,
            vol.Required(CONF_PASSWORD): cv.string
        })
    },
    extra=vol.ALLOW_EXTRA
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """
  AUX Cloud setup using configuration from configuration.yaml
  """

    hass.data[DATA_AUX_CLOUD_CONFIG] = config.get(DOMAIN, {})
    hass.data[DATA_HASS_CONFIG] = config

    if not hass.config_entries.async_entries(DOMAIN) and hass.data[DATA_AUX_CLOUD_CONFIG]:
        # No config entry exists and configuration.yaml config exists, trigger the import flow.
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AUX Cloud via a config entry."""
    # Get credentials from configuration.yaml if available, otherwise from config entry
    config = hass.data.get(DATA_AUX_CLOUD_CONFIG, {})

    email = config.get(CONF_EMAIL, entry.data.get(CONF_EMAIL))
    password = config.get(CONF_PASSWORD, entry.data.get(CONF_PASSWORD))

    # Ensure we have the required credentials
    if not email or not password:
        _LOGGER.error("Missing required credentials for AUX Cloud")
        return False

    data = AuxCloudData(hass, entry, email=email, password=password)

    if not await data.refresh():
        return False

    await data.update()

    devices = await data.aux_cloud.async_get_devices()
    if not devices:
        _LOGGER.error("No AUX Cloud devices found to set up")
        return False

    hass.data[DOMAIN] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


class AuxCloudData:
    def __init__(
            self, hass: HomeAssistant, entry: ConfigEntry, email: str, password: str
    ) -> None:
        """Initialize the Aux Cloud data object."""
        self._hass = hass
        self._entry = entry
        self._email = email
        self._password = password
        self.aux_cloud = AuxCloudAPI()
        self.aux_cloud = AuxCloudAPI()

    async def async_setup(self):
        """Perform async setup."""
        await self.aux_cloud.login(self._email, self._password)

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def update(self):
        """Get the latest data from AUX Cloud"""
        try:
            await self._hass.async_add_executor_job(self.aux_cloud.update)
            _LOGGER.debug("Updating AUX Cloud")
        except Exception as e:  # Replace with specific exception when implemented
            _LOGGER.debug("Relogging to AUX Cloud due to: %s", e)
            await self.refresh()

    async def refresh(self) -> bool:
        """Refresh AUX Cloud credentials and update config entry."""
        _LOGGER.debug("Refreshing AUX Cloud credentials")

        # Use the credentials from configuration.yaml if available
        config = self._hass.data.get(DATA_AUX_CLOUD_CONFIG, {})
        email = config.get(CONF_EMAIL, self._email)
        password = config.get(CONF_PASSWORD, self._password)

        if await self._hass.async_add_executor_job(
                lambda: self.aux_cloud.login(email, password)
        ):
            # Update the stored credentials to match the current ones
            self._email = email
            self._password = password

            # Only update the config entry if we're not using configuration.yaml credentials
            if not config.get(CONF_EMAIL) and not config.get(CONF_PASSWORD):
                self._hass.config_entries.async_update_entry(
                    self._entry,
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                    },
                )
            return True

        _LOGGER.error("Error refreshing AUX Cloud")
        return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry and platforms."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop(DOMAIN)
    return unload_ok
