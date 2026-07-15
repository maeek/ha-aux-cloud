import base64
import binascii
import json
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.const import AC_FAN_SPEED, AuxProducts
from .const import (
    _LOGGER,
    DEFAULT_AC_FAN_MODES,
    DOMAIN,
    FAN_MODE_HA_TO_AUX,
    MANUFACTURER,
)


def get_ac_fan_modes(device: dict[str, Any]) -> list[str]:
    """Return fan modes advertised by the device profile."""
    fallback = list(DEFAULT_AC_FAN_MODES)

    try:
        cookie = json.loads(base64.b64decode(device.get("cookie", ""), validate=True))
        if not isinstance(cookie, dict):
            return fallback
        profile = cookie.get("profile")
        if isinstance(profile, str):
            profile = json.loads(profile)
    except (binascii.Error, json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return fallback

    if not isinstance(profile, dict):
        return fallback

    suids = profile.get("suids", [])
    if not isinstance(suids, list):
        return fallback

    supported_values = set()
    for suid in suids:
        if not isinstance(suid, dict) or not isinstance(suid.get("intfs"), dict):
            continue
        entries = suid["intfs"].get(AC_FAN_SPEED, [])
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("in"), list):
                continue
            encoded_values = entry["in"]
            # Broadlink prefixes enumerated values with the type marker 1.
            if not encoded_values or encoded_values[0] != 1:
                continue
            supported_values.update(
                value
                for value in encoded_values[1:]
                if isinstance(value, int) and not isinstance(value, bool)
            )

    modes = [
        mode for mode, value in FAN_MODE_HA_TO_AUX.items() if value in supported_values
    ]
    return modes or fallback


class DeviceStateHelper:
    """Helper class to manage device parameters state, failsafe, and optimistic updates."""

    def __init__(self, initial_params: dict[str, Any], max_failed_polls: int):
        self._cached_params: dict[str, Any] = initial_params.copy() if initial_params else {}
        self._failed_poll_count = 0
        self._max_failed_polls = max_failed_polls
        self._backup_params: dict[str, Any] = {}
        self._last_logged_payload: str | None = None
        self._last_processed_update_id: int | None = None

    @property
    def current_params(self) -> dict[str, Any]:
        """Return the current verified parameters."""
        return self._cached_params

    def is_available(self) -> bool:
        """Determines if the entity should be marked as available."""
        return bool(len(self._cached_params) > 0 and self._failed_poll_count <= self._max_failed_polls)

    def process_new_payload(
        self,
        current_params: dict[str, Any],
        device_name: str,
        update_id: int | None = None,
    ):
        """Orchestrates the processing of incoming payloads."""
        if update_id is not None and update_id == self._last_processed_update_id:
            return

        if update_id is not None:
            self._last_processed_update_id = update_id

        self._log_payload_if_changed(current_params, device_name)

        if not current_params:
            self._handle_empty_payload(device_name)
            return

        self._handle_valid_payload(current_params, device_name)

    def _log_payload_if_changed(self, current_params: dict[str, Any], device_name: str):
        """Logs the raw payload only if it differs from the last logged one."""
        current_payload_str = str(current_params)
        if current_payload_str != self._last_logged_payload:
            _LOGGER.debug("State changed or new poll. Raw payload for %s: %s", device_name, current_params)
            self._last_logged_payload = current_payload_str

    def _handle_empty_payload(self, device_name: str):
        """Handles network errors or empty responses, managing the failsafe counter."""
        self._failed_poll_count += 1

        if self._failed_poll_count <= self._max_failed_polls:
            _LOGGER.warning(
                "Empty payload for device %s (Attempt %s/%s). Using cache to prevent flapping.",
                device_name, self._failed_poll_count, self._max_failed_polls
            )
            return

        if self._failed_poll_count == self._max_failed_polls + 1:
            _LOGGER.error(
                "Device %s dropped connection for %s polls. Marking as unavailable.",
                device_name, self._failed_poll_count
            )
            self._cached_params = {}

    def _handle_valid_payload(self, current_params: dict[str, Any], device_name: str):
        """Merges a valid partial or full payload into the cache and resets counters."""
        if self._failed_poll_count > 0:
            _LOGGER.info(
                "Device %s connection restored after %s failed attempts.",
                device_name, self._failed_poll_count
            )

        self._failed_poll_count = 0
        self._cached_params.update(current_params)

    def apply_optimistic(self, new_params: dict[str, Any]):
        """Applies new params optimistically and saves a backup for rollback."""
        self._backup_params.clear()

        for key, value in new_params.items():
            if key in self._cached_params:
                self._backup_params[key] = self._cached_params[key]
            self._cached_params[key] = value

        self._last_logged_payload = None

    def rollback(self, failed_params: dict[str, Any]):
        """Rolls back the optimistic update if API call fails."""
        for key in failed_params:
            if key in self._backup_params:
                self._cached_params[key] = self._backup_params[key]
            else:
                self._cached_params.pop(key, None)
        self._backup_params.clear()
        self._last_logged_payload = None


class BaseEntity(CoordinatorEntity):
    """Base class for all AUX Cloud entities."""

    def __init__(self, coordinator: Any, device_id: str, entity_description: Any):
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = self.coordinator.get_device_by_endpoint_id(self._device_id)
        self._attr_has_entity_name = True
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{DOMAIN}_{self._device_id.lstrip('0')}_{self.entity_description.key}"
        )

        initial_params = self._device.get("params", {}) if self._device else {}
        self._state_helper = self.coordinator.get_state_helper(
            self._device_id,
            initial_params,
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID for the entity."""
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        info = DeviceInfo(
            identifiers={(DOMAIN, str(self._device_id))},
            name=str(self._device.get("friendlyName", "AUX")),
            manufacturer=MANUFACTURER,
            model=str(AuxProducts.get_device_name(self._device.get("productId", None))),
        )

        if "mac" in self._device and self._device["mac"]:
            info["connections"] = {(CONNECTION_NETWORK_MAC, str(self._device["mac"]))}

        return info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
                self._device is not None
                and self._device.get("endpointId") is not None
                and self._state_helper.is_available()
        )

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        device_from_coordinator = self.coordinator.get_device_by_endpoint_id(self._device_id)
        self._device = device_from_coordinator or {}

        raw_params = self._device.get("params", {})
        device_name = self._device.get("friendlyName", self._device_id)

        # Helper is now the source of truth for params
        self._state_helper.process_new_payload(
            raw_params,
            device_name,
            update_id=id(self.coordinator.data),
        )

        self.async_write_ha_state()

    def _get_device_params(self) -> dict[str, Any]:
        """Get device parameters securely from the state helper."""
        return self._state_helper.current_params

    async def _set_device_params(self, params: dict[str, Any]):
        """Set parameters on the device using Optimistic Updates via Helper."""
        device_name = self._device.get("friendlyName", self._device_id)
        _LOGGER.debug("Optimistically setting %s for device %s", params, device_name)

        # Apply changes to the internal state immediately
        self._state_helper.apply_optimistic(params)
        self.async_write_ha_state()

        try:
            await self.coordinator.api.set_device_params(self._device, params)
            # Refresh coordinator to sync all dependent entities immediately after a successful write
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to apply setting %s to %s: %s", params, device_name, err)
            self._state_helper.rollback(params)
            self.async_write_ha_state()
            raise
