"""Diagnostics support for AUX Cloud."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .api.models import AuxDevice
from .const import CONF_PHONE_NUMBER
from .coordinator import AuxCloudConfigEntry
from .device_metadata import (
    AUX_QUERY_FAILURES,
    get_cookie_profile_params,
    get_protocol_version_details,
)
from .devices import get_device_profile

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


def _device_diagnostics(device: Mapping[str, Any]) -> dict[str, Any]:
    """Return useful device metadata without cloud identity or parameter values."""
    profile = get_device_profile(device)
    device_snapshot = cast(AuxDevice, dict(device))
    cookie_params = set(get_cookie_profile_params(device))
    profile_params = set(profile.params)
    protocol_version, protocol_version_source = get_protocol_version_details(device)
    return {
        "product_id": device.get("productId"),
        "state": device.get("state"),
        "profile": profile.model_name,
        "device_type": profile.device_type,
        "protocol_version": protocol_version,
        "protocol_version_source": protocol_version_source,
        "supported_params": sorted(profile_params),
        "writable_params": sorted(profile.writable_params),
        "initial_param_queries": profile.initial_param_queries(device_snapshot),
        "fallback_param_queries": profile.fallback_param_queries(device_snapshot),
        "cookie_profile_params": sorted(cookie_params),
        "cookie_only_params": sorted(cookie_params - profile_params),
        "profile_only_params": (
            sorted(profile_params - cookie_params) if cookie_params else []
        ),
        "reported_param_names": sorted(device.get("params", {})),
        "query_failures": device.get(AUX_QUERY_FAILURES, []),
    }


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant, entry: AuxCloudConfigEntry
) -> dict[str, Any]:
    """Return redacted config and coordinator diagnostics."""
    coordinator = entry.runtime_data
    devices = list(coordinator.data.values()) if coordinator.data else []
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
