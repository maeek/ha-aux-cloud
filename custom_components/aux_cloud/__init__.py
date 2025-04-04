"""Aux Cloud integration for Home Assistant."""

from datetime import timedelta
import asyncio

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
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_EMAIL): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
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

    if (
        not hass.config_entries.async_entries(DOMAIN)
        and hass.data[DATA_AUX_CLOUD_CONFIG]
    ):
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

    def __init__(
        self,
        hass: HomeAssistant,
        api: AuxCloudAPI,
        email: str,
        password: str,
        selected_device_ids: list,
    ):
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
        _LOGGER.debug("AUX Cloud Coordinator initialized with email: %s", email)

    def get_device_by_endpoint_id(self, endpoint_id: str):
        """Get a device by its endpoint ID."""
        if not self.devices:
            return None
        for device in self.devices:
            if device["endpointId"] == endpoint_id:
                return device
        return None

    async def _async_update_data(self):
        """Fetch data from AUX Cloud."""
        _LOGGER.debug("Updating AUX Cloud data...")

        try:
            if not self.api.is_logged_in():
                # Attempt to log in
                _LOGGER.debug("Logging into AUX Cloud API...")
                login_success = await self.api.login(self.email, self.password)
                if not login_success:
                    raise UpdateFailed("Login to AUX Cloud API failed")

            if self.api.families is None:
                _LOGGER.debug("Fetching families from AUX Cloud API...")
                await self.api.get_families()

            # Create a single list of tasks for fetching devices (shared and non-shared)
            device_tasks = []
            shared_device_tasks = []

            for family_id in self.api.families:
                device_tasks.append(
                    self.api.get_devices(
                        family_id,
                        shared=False,
                        selected_devices=self.selected_device_ids,
                    )
                )
                shared_device_tasks.append(
                    self.api.get_devices(
                        family_id,
                        shared=True,
                        selected_devices=self.selected_device_ids,
                    )
                )

            # Run all tasks concurrently
            devices_results = await asyncio.gather(
                *device_tasks, return_exceptions=True
            )
            shared_devices_results = await asyncio.gather(
                *shared_device_tasks, return_exceptions=True
            )

            # Process results and handle exceptions
            all_devices = []
            for result in devices_results + shared_devices_results:
                if isinstance(result, Exception):
                    # Log the error for the specific task
                    _LOGGER.error(f"Error fetching devices: {result}")
                    continue  # Skip this result and move to the next one
                # Add the successful result to the list of all devices
                all_devices.extend(result or [])

            # Filter devices if selected_device_ids is provided
            if self.selected_device_ids:
                self.devices = [
                    device
                    for device in all_devices
                    if device["endpointId"] in self.selected_device_ids
                ]
            else:
                self.devices = all_devices

            _LOGGER.debug("Fetched AUX Cloud data: %s devices", len(self.devices))

            return {"devices": self.devices}

        except Exception as e:
            _LOGGER.error(f"Error updating AUX Cloud data: {e}")
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

    # Attempt to log in
    try:
        login_success = await api.login(email, password)
        if not login_success:
            _LOGGER.error("Login to AUX Cloud API failed")
            return False
    except Exception as e:
        _LOGGER.error(f"Exception during login: {e}")
        return False

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
