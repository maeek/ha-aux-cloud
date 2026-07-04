"""Aux Cloud integration for Home Assistant."""

import asyncio

import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import AuxCloudAPI
from .const import (
    _LOGGER,
    CONF_PHONE_COUNTRY_CODE,
    CONF_PHONE_NUMBER,
    CONF_SELECTED_DEVICES,
    DATA_AUX_CLOUD_CONFIG,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import (
    FALLBACK_SCAN_INTERVAL,
    WEBSOCKET_SETUP_RETRY_INITIAL_DELAY,
    WEBSOCKET_SETUP_RETRY_MAX_DELAY,
    AuxCloudCoordinator,
)

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

    hass.data[DATA_AUX_CLOUD_CONFIG] = config.get(DOMAIN, {})

    if (
        not hass.config_entries.async_entries(DOMAIN)
        and hass.data[DATA_AUX_CLOUD_CONFIG]
    ):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=config[DOMAIN]
            )
        )
        _LOGGER.info(
            "AUX Cloud configured via configuration.yaml. For better security, "
            "it is recommended to configure this integration through the UI where "
            "credentials are stored encrypted."
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AUX Cloud from a config entry."""
    region = entry.data.get(CONF_REGION, "eu")
    api = AuxCloudAPI(region=region, session=async_get_clientsession(hass))
    email = entry.data.get(CONF_EMAIL)
    phone_number = entry.data.get(CONF_PHONE_NUMBER)
    phone_country_code = entry.data.get(CONF_PHONE_COUNTRY_CODE)
    password = entry.data.get(CONF_PASSWORD)
    selected_device_ids = entry.data.get(CONF_SELECTED_DEVICES, [])

    if not password or not (email or phone_number):
        raise ConfigEntryAuthFailed("Missing required credentials for AUX Cloud")

    coordinator = AuxCloudCoordinator(
        hass,
        api,
        email,
        password,
        selected_device_ids,
        phone_number=phone_number,
        phone_country_code=phone_country_code,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
    }

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except asyncio.CancelledError:
        await _async_cleanup_entry_data(hass, entry.entry_id)
        raise
    except Exception:
        await _async_cleanup_entry_data(hass, entry.entry_id)
        raise

    await coordinator.async_start_websocket()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry and platforms."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await _async_cleanup_entry_data(hass, entry.entry_id)
    return unload_ok


async def _async_cleanup_entry_data(hass: HomeAssistant, entry_id: str) -> None:
    """Close coordinator resources and remove stored entry data."""
    entry_data = hass.data.get(DOMAIN, {}).pop(entry_id, None)
    if entry_data is not None:
        await entry_data["coordinator"].async_close()
    if not hass.data.get(DOMAIN):
        hass.data.pop(DOMAIN, None)


__all__ = [
    "AuxCloudCoordinator",
    "FALLBACK_SCAN_INTERVAL",
    "WEBSOCKET_SETUP_RETRY_INITIAL_DELAY",
    "WEBSOCKET_SETUP_RETRY_MAX_DELAY",
]
