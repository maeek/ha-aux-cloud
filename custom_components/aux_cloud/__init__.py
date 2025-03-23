"""Aux Cloud integration for Home Assistant."""
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import Throttle

from .api.aux_cloud import AuxCloudAPI
from .const import (
    _LOGGER,
    DOMAIN,
    DATA_AUX_CLOUD_CONFIG,
    DATA_HASS_CONFIG,
    PLATFORMS,
    CONF_SELECTED_DEVICES,
)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=180)

# Schema to include email and password (device selection is handled in config flow)
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema({
            vol.Required(CONF_EMAIL): cv.string,
            vol.Required(CONF_PASSWORD): cv.string,
        })
    },
    extra=vol.ALLOW_EXTRA
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """
    AUX Cloud setup for configuration.yaml import.
    This is mainly kept for backward compatibility.
    UI configuration is recommended for better security.
    """
    if DOMAIN not in config:
        return True

    hass.data[DATA_AUX_CLOUD_CONFIG] = config.get(DOMAIN, {})

    if not hass.config_entries.async_entries(DOMAIN) and hass.data[DATA_AUX_CLOUD_CONFIG]:
        # Import from configuration.yaml if no config entry exists
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=config[DOMAIN]
            )
        )

        # Log a message about UI configuration being preferred
        _LOGGER.info(
            "AUX Cloud configured via configuration.yaml. For better security, "
            "it is recommended to configure this integration through the UI where "
            "credentials are stored encrypted."
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AUX Cloud via a config entry."""
    # Get credentials from config entry
    email = entry.data.get(CONF_EMAIL)
    password = entry.data.get(CONF_PASSWORD)
    selected_device_ids = entry.data.get(CONF_SELECTED_DEVICES, [])

    # Ensure we have the required credentials
    if not email or not password:
        _LOGGER.error("Missing required credentials for AUX Cloud")
        return False

    data = AuxCloudData(hass, entry, email=email, password=password, selected_device_ids=selected_device_ids)

    if not await data.refresh():
        return False

    await data.update()

    # Store the data for platform use
    hass.data[DOMAIN] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


class AuxCloudData:
    def __init__(
            self, hass: HomeAssistant, entry: ConfigEntry, email: str, password: str,
            selected_device_ids: list = None
    ) -> None:
        """Initialize the Aux Cloud data object."""
        self._hass = hass
        self._entry = entry
        self._email = email
        self._password = password
        self.aux_cloud = AuxCloudAPI()
        self.selected_device_ids = selected_device_ids or []
        self.devices = []
        self.families = {}

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

        try:
            # Login
            await self.aux_cloud.login(self._email, self._password)

            # Fetch all families and their devices
            await self.async_setup_families()

            return True
        except Exception as e:
            _LOGGER.error("Error refreshing AUX Cloud: %s", e)
            return False

    async def async_setup_families(self):
        """Setup families and devices."""
        family_data = await self.aux_cloud.list_families()
        self.families = {}
        all_devices = []

        for family in family_data:
            family_id = family['familyid']
            self.families[family_id] = {
                'id': family_id,
                'name': family['name'],
                'rooms': [],
                'devices': []
            }

            # Get rooms if needed
            rooms = await self.aux_cloud.list_rooms(family_id)
            if rooms:
                self.families[family_id]['rooms'] = rooms

            # Get devices for this family
            devices = await self.aux_cloud.list_devices(family_id)
            shared_devices = await self.aux_cloud.list_devices(family_id, shared=True)

            family_devices = devices + shared_devices
            all_devices.extend(family_devices)

            # Add devices to family in memory
            self.families[family_id]['devices'] = family_devices

        # Filter devices if selected_device_ids is provided
        if self.selected_device_ids:
            self.devices = [
                device for device in all_devices
                if device['endpointId'] in self.selected_device_ids
            ]
        else:
            self.devices = all_devices

        _LOGGER.debug(f"Found {len(self.devices)} devices out of {len(all_devices)} total devices")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry and platforms."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop(DOMAIN)
    return unload_ok
