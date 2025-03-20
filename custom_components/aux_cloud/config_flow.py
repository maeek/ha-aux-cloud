"""Config flow to configure Aux Cloud."""

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, SOURCE_IMPORT
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.selector import selector

from .api.aux_cloud import AuxCloudAPI
from .const import DATA_AUX_CLOUD_CONFIG, DOMAIN


class AuxCloudFlowHandler(ConfigFlow, domain=DOMAIN):
  """Handle an AUX Cloud config flow."""

  VERSION = 1

  def __init__(self) -> None:
    """Initialize the AUX Cloud flow."""
    self._aux_cloud = None

  async def async_step_user(self, user_input=None):
    """Handle a flow initiated by the user."""
    if self._async_current_entries():
      # Config entry already exists, only one allowed.
      return self.async_abort(reason="single_instance_allowed")

    errors = {}
    stored_email = (
        self.hass.data[DATA_AUX_CLOUD_CONFIG].get(CONF_EMAIL)
        if DATA_AUX_CLOUD_CONFIG in self.hass.data
        else ""
    )
    stored_password = (
        self.hass.data[DATA_AUX_CLOUD_CONFIG].get(CONF_PASSWORD)
        if DATA_AUX_CLOUD_CONFIG in self.hass.data
        else ""
    )

    if user_input is not None:
      self._aux_cloud = AuxCloudAPI(
        email=user_input[CONF_EMAIL], password=user_input[CONF_PASSWORD])

      if await self.hass.async_add_executor_job(self._aux_cloud.login):
        config = {
            CONF_EMAIL: self._aux_cloud.email,
            CONF_PASSWORD: self._aux_cloud.password,
        }
        return self.async_create_entry(title=DOMAIN, data=config)
      errors["base"] = "user_login_failed"

    data_schema = {
      vol.Required(CONF_EMAIL, default=stored_email): str,
      vol.Required(CONF_PASSWORD, default=stored_password): str
    }

    if self.show_advanced_options:
      data_schema["allow_groups"] = selector({
          "select": {
              "options": ["eu", "us"],
          }
      })

    return self.async_show_form(
        step_id="user",
        data_schema=vol.Schema(data_schema),
        errors=errors,
    )

  async def async_step_import(self, import_info):
    """Import a config entry from configuration.yaml."""
    # Check if we already have a config entry
    if self._async_current_entries():
      return self.async_abort(reason="single_instance_allowed")

    # Process the import_info
    if import_info and CONF_EMAIL in import_info and CONF_PASSWORD in import_info:
      return await self.async_step_user(import_info)

    # If import data is incomplete, show the form
    return await self.async_step_user()