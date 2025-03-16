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

CONFIG_SCHEMA = vol.Schema(
  {
    DOMAIN: vol.Schema({
      vol.Optional(CONF_EMAIL): cv.string
    })
  },
  extra=vol.ALLOW_EXTRA
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
  """
  AUX Cloud uses config flow for configuration.
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
  """Set up ecobee via a config entry."""
  email = entry.data[CONF_EMAIL]
  password = entry.data[CONF_PASSWORD]

  data = AuxCloudData(hass, entry, email=email, password=password)

  if not await data.refresh():
    return False

  await data.update()

  if data.ecobee.thermostats is None:
    _LOGGER.error("No ecobee devices found to set up")
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
    self.aux_cloud = AuxCloudAPI()
    self.aux_cloud.login(email, password)

  @Throttle(MIN_TIME_BETWEEN_UPDATES)
  async def update(self):
    """Get the latest data from AUX Cloud"""
    # try:
    await self._hass.async_add_executor_job(self.aux_cloud.update)
    _LOGGER.debug("Updating AUX Cloud")
    # TODO: Implement
    # except ExpiredTokenError:
    #   _LOGGER.debug("Relogging to AUX Cloud")
    #   await self.login()

  async def refresh(self) -> bool:
    """Refresh AUX Cloud credentials and update config entry."""
    _LOGGER.debug("Refreshing AUX CLoud credentials and updating config entry")
    if await self._hass.async_add_executor_job(self.aux_cloud.login):
      self._hass.config_entries.async_update_entry(
          self._entry,
          data={
              CONF_EMAIL: self.aux_cloud[CONF_EMAIL],
              CONF_PASSWORD: self.aux_cloud[CONF_PASSWORD],
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
