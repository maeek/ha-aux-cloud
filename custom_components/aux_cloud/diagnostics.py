"""Diagnostics support for AUX Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_PHONE_NUMBER
from .devices.profiles import (
    AUX_QUERY_FAILURES,
    get_product_profile,
    get_protocol_version,
)
from .models import AuxCloudConfigEntry

TO_REDACT = {
    "account_id",
    "cookie",
    "devSession",
    "email",
    "endpointId",
    "friendlyName",
    "gatewayId",
    "mac",
    "password",
    CONF_PHONE_NUMBER,
}


def _device_diagnostics(device: dict[str, Any]) -> dict[str, Any]:
    """Return useful device metadata without cloud identity or parameter values."""
    profile = get_product_profile(device.get("productId"))
    return {
        "product_id": device.get("productId"),
        "state": device.get("state"),
        "profile": profile.model_name,
        "device_type": profile.device_type,
        "protocol_version": get_protocol_version(device),
        "supported_params": sorted(profile.params),
        "writable_params": sorted(profile.writable_params),
        "reported_param_names": sorted(device.get("params", {})),
        "query_failures": device.get(AUX_QUERY_FAILURES, []),
        "last_updated": device.get("last_updated"),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AuxCloudConfigEntry
) -> dict[str, Any]:
    """Return redacted config and coordinator diagnostics."""
    coordinator = entry.runtime_data.coordinator
    devices = coordinator.data["devices"] if coordinator.data else []
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "runtime": {
            "device_count": len(devices),
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            "websocket_degraded": coordinator.websocket_degraded,
        },
        "devices": [_device_diagnostics(device) for device in devices],
    }
