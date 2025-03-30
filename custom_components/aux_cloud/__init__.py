"""Aux Cloud integration for Home Assistant."""
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.aux_cloud import AuxCloudAPI
from .const import (
    _LOGGER,
    DOMAIN,
    DATA_AUX_CLOUD_CONFIG,
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


class AuxCloudCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator for AUX Cloud."""

    def __init__(self, hass: HomeAssistant, api: AuxCloudAPI, email: str, password: str, selected_device_ids: list):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="AUX Cloud Coordinator",
            update_interval=MIN_TIME_BETWEEN_UPDATES,
        )
        self.api = api
        self.email = email
        self.password = password
        self.selected_device_ids = selected_device_ids
        self.devices = []
        self.families = {}

    async def _async_update_data(self):
        """Fetch data from AUX Cloud."""
        try:
            if not await self.api.is_logged_in():
                await self.api.login(self.email, self.password)

            # Fetch families and devices
            family_data = await self.api.list_families()
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

                # Fetch devices
                devices = await self.api.list_devices(family_id) or []
                shared_devices = await self.api.list_devices(family_id, shared=True) or []

                # Deduplicate devices
                seen_endpoint_ids = set()
                family_devices = []
                for device in devices + shared_devices:
                    if device['endpointId'] not in seen_endpoint_ids:
                        seen_endpoint_ids.add(device['endpointId'])
                        family_devices.append(device)
                all_devices.extend(family_devices)

                self.families[family_id]['devices'] = family_devices

            # Filter devices if selected_device_ids is provided
            if self.selected_device_ids:
                self.devices = [
                    device for device in all_devices
                    if device['endpointId'] in self.selected_device_ids
                ]
            else:
                self.devices = all_devices

            return {"devices": self.devices, "families": self.families}

        except Exception as e:
            raise UpdateFailed(f"Error updating AUX Cloud data: {e}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AUX Cloud via a config entry."""
    email = entry.data.get(CONF_EMAIL)
    password = entry.data.get(CONF_PASSWORD)
    selected_device_ids = entry.data.get(CONF_SELECTED_DEVICES, [])

    if not email or not password:
        _LOGGER.error("Missing required credentials for AUX Cloud")
        return False

    api = AuxCloudAPI()
    coordinator = AuxCloudCoordinator(hass, api, email, password, selected_device_ids)

    # Perform an initial update
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator for platform use
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry and platforms."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop(DOMAIN)
    return unload_ok
