"""Aux Cloud integration for Home Assistant."""

import asyncio
import logging

import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import AuxCloudAPI
from .const import (
    CONF_ACCOUNT_ID,
    CONF_FAMILIES,
    CONF_PHONE_NUMBER,
    CONF_SELECTED_DEVICES,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import (
    FALLBACK_SCAN_INTERVAL,
    AuxCloudCoordinator,
)
from .identifiers import account_unique_id_from_user_id

_LOGGER = logging.getLogger(__name__)

type AuxCloudConfigEntry = ConfigEntry[AuxCloudCoordinator]

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
    """Set up AUX Cloud configuration.yaml import."""
    if DOMAIN not in config:
        return True

    if not hass.config_entries.async_entries(DOMAIN) and config.get(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=config[DOMAIN]
            )
        )
        _LOGGER.info(
            "AUX Cloud was imported from configuration.yaml; use the UI for future "
            "credential updates"
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: AuxCloudConfigEntry) -> bool:
    """Set up AUX Cloud from a config entry."""
    region = entry.data.get(CONF_REGION, "eu")
    api = AuxCloudAPI(region=region, session=async_get_clientsession(hass))
    email = entry.data.get(CONF_EMAIL)
    phone_number = entry.data.get(CONF_PHONE_NUMBER)
    password = entry.data.get(CONF_PASSWORD)
    if not password or not (email or phone_number):
        raise ConfigEntryAuthFailed("Missing required credentials for AUX Cloud")

    coordinator = AuxCloudCoordinator(
        hass,
        api,
        config_entry=entry,
    )

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    if not entry.data.get(CONF_ACCOUNT_ID) and api.user_id:
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_ACCOUNT_ID: account_unique_id_from_user_id(region, api.user_id),
            },
        )

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except (asyncio.CancelledError, Exception):
        await coordinator.async_close()
        raise

    coordinator.start_realtime()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AuxCloudConfigEntry) -> bool:
    """Unload the config entry and platforms."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_close()
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy entries without changing any registry identifiers."""
    if entry.version > 2 or (entry.version == 2 and entry.minor_version > 1):
        return False
    if entry.version == 2 and entry.minor_version == 1:
        return True

    migrated_data = dict(entry.data)
    if entry.version < 2:
        migrated_data = {
            key: value
            for key, value in entry.data.items()
            if key not in {CONF_FAMILIES, CONF_SELECTED_DEVICES}
        }
    hass.config_entries.async_update_entry(
        entry,
        data=migrated_data,
        version=2,
        minor_version=1,
    )
    _LOGGER.info("Migrated AUX Cloud config entry to version 2")
    return True


async def async_remove_config_entry_device(
    _hass: HomeAssistant,
    entry: AuxCloudConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow manual removal only when a device is absent from cloud inventory."""
    active_endpoint_ids = {
        device["endpointId"]
        for device in (entry.runtime_data.data or {}).values()
        if device.get("endpointId")
    }
    return not any(
        identifier[0] == DOMAIN and identifier[1] in active_endpoint_ids
        for identifier in device_entry.identifiers
    )


__all__ = [
    "FALLBACK_SCAN_INTERVAL",
    "AuxCloudCoordinator",
]
