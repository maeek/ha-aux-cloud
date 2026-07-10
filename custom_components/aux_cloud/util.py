from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AuxApiError
from .const import _LOGGER, DOMAIN, MANUFACTURER
from .devices.profiles import AC_TEMPERATURE_AMBIENT, AuxProducts

if TYPE_CHECKING:
    from .coordinator import AuxCloudCoordinator  # noqa: F401


def deduplicate_devices_by_endpoint_id(devices: Iterable[dict]) -> list[dict]:
    """Return devices in source order, keeping the first entry per endpoint ID."""
    deduplicated = []
    seen_endpoint_ids = set()

    for device in devices:
        endpoint_id = device.get("endpointId")
        if endpoint_id is None:
            deduplicated.append(device)
            continue

        if endpoint_id in seen_endpoint_ids:
            _LOGGER.debug("Skipping duplicate AUX Cloud device entry")
            continue

        seen_endpoint_ids.add(endpoint_id)
        deduplicated.append(device)

    return deduplicated


def deduplicate_ordered_values(values: Iterable[str]) -> list[str]:
    """Return values in source order with duplicates removed."""
    deduplicated = []
    seen_values = set()

    for value in values:
        if value in seen_values:
            continue
        seen_values.add(value)
        deduplicated.append(value)

    return deduplicated


def supported_entity_definitions(
    device: dict[str, Any], definitions: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return entity definitions backed by a device product profile."""
    product_id = device.get("productId")
    if not product_id:
        return []
    supported_params = {
        *(AuxProducts.get_params_list(product_id) or ()),
        *(AuxProducts.get_special_params_list(product_id) or ()),
    }
    return [
        definition
        for definition in definitions
        if definition["description"].key in supported_params
    ]


def account_unique_id_from_credentials(
    region: str,
    *,
    email: str | None = None,
    phone_number: str | None = None,
) -> str | None:
    """Return the stable AUX Cloud account unique ID for a config entry."""
    normalized_region = (region or "eu").strip().lower()

    if email:
        return f"{normalized_region}:email:{email.strip().lower()}"

    if phone_number:
        normalized_phone_number = "".join(
            character for character in phone_number if character.isdigit()
        )
        if normalized_phone_number:
            return f"{normalized_region}:phone:{normalized_phone_number}"

    return None


def account_unique_id_from_user_id(region: str, user_id: str) -> str:
    """Return the stable account ID used for newly authenticated entries."""
    return f"{(region or 'eu').strip().lower()}:user:{user_id}"


def legacy_entity_unique_id(endpoint_id: str, entity_key: str) -> str:
    """Return the immutable unique ID used by all released AUX entities.

    Do not change this formula. Existing entity-registry rows depend on it.
    """
    return f"{DOMAIN}_{endpoint_id.lstrip('0')}_{entity_key}"


def device_identifier(endpoint_id: str) -> tuple[str, str]:
    """Return the immutable raw endpoint device-registry identifier."""
    return (DOMAIN, endpoint_id)


def collision_safe_entity_unique_id(
    hass: Any,
    entity_domain: str,
    endpoint_id: str,
    entity_key: str,
    reserved: set[tuple[str, str]],
    *,
    config_entry_id: str | None = None,
    identity_salt: str = "",
) -> str:
    """Preserve legacy IDs and use deterministic V2 IDs only for collisions."""
    legacy_id = legacy_entity_unique_id(endpoint_id, entity_key)
    digest_source = f"{endpoint_id}\0{identity_salt}"
    digest = hashlib.sha256(digest_source.encode()).hexdigest()[:8]
    candidates = (legacy_id, f"{legacy_id}_v2_{digest}")
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    for candidate in candidates:
        reservation = (entity_domain, candidate)
        matching_entries = [
            entry
            for entry in entity_registry.entities.values()
            if entry.domain == entity_domain
            and entry.platform == DOMAIN
            and entry.unique_id == candidate
        ]
        for entry in matching_entries:
            if config_entry_id is not None:
                if entry.config_entry_id == config_entry_id:
                    reserved.add(reservation)
                    return candidate
                continue
            device = (
                device_registry.async_get(entry.device_id) if entry.device_id else None
            )
            if device and device_identifier(endpoint_id) in device.identifiers:
                reserved.add(reservation)
                return candidate
        if not matching_entries and reservation not in reserved:
            reserved.add(reservation)
            return candidate

    # A SHA-256 prefix collision is extraordinarily unlikely. Keeping the full
    # endpoint digest makes this final fallback deterministic too.
    unique_id = f"{legacy_id}_v2_{hashlib.sha256(digest_source.encode()).hexdigest()}"
    reserved.add((entity_domain, unique_id))
    return unique_id


class DeviceStateHelper:
    """Helper class to manage device parameters state, failsafe, and optimistic updates."""

    def __init__(self, initial_params: dict[str, Any], max_failed_polls: int):
        self._cached_params: dict[str, Any] = (
            initial_params.copy() if initial_params else {}
        )
        self._failed_poll_count = 0
        self._max_failed_polls = max_failed_polls
        self._last_logged_payload: str | None = None
        self._last_processed_update_id: int | None = None

    @property
    def current_params(self) -> dict[str, Any]:
        """Return the current verified parameters."""
        return self._cached_params

    def is_available(self) -> bool:
        """Determines if the entity should be marked as available."""
        return bool(
            len(self._cached_params) > 0
            and self._failed_poll_count <= self._max_failed_polls
        )

    def mark_unavailable(self, _device_name: str) -> bool:
        """Mark the device unavailable because the cloud explicitly says it is offline."""
        was_available = self.is_available()
        if was_available:
            _LOGGER.info("AUX device is offline; marking entities unavailable")
        self._cached_params = {}
        self._failed_poll_count = self._max_failed_polls + 1
        self._last_logged_payload = None
        return was_available

    def replace_params(self, params: dict[str, Any]) -> None:
        """Replace cached state after an authoritative rollback or snapshot."""
        self._cached_params = dict(params)
        self._failed_poll_count = 0 if params else self._max_failed_polls + 1
        self._last_logged_payload = None

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

    def _log_payload_if_changed(
        self, current_params: dict[str, Any], _device_name: str
    ):
        """Track payload changes without logging private cloud state."""
        current_payload_str = str(current_params)
        if current_payload_str != self._last_logged_payload:
            _LOGGER.debug("AUX device state changed")
            self._last_logged_payload = current_payload_str

    def _handle_empty_payload(self, _device_name: str):
        """Handles network errors or empty responses, managing the failsafe counter."""
        self._failed_poll_count += 1

        if self._failed_poll_count <= self._max_failed_polls:
            _LOGGER.warning(
                "Empty AUX device payload (attempt %s/%s); retaining cached state",
                self._failed_poll_count,
                self._max_failed_polls,
            )
            return

        if self._failed_poll_count == self._max_failed_polls + 1:
            _LOGGER.error(
                "AUX device was unavailable for %s polls; marking entities unavailable",
                self._failed_poll_count,
            )
            self._cached_params = {}

    def _handle_valid_payload(self, current_params: dict[str, Any], _device_name: str):
        """Merges a valid partial or full payload into the cache and resets counters."""
        if self._failed_poll_count > 0:
            _LOGGER.info(
                "AUX device connection restored after %s failed attempts",
                self._failed_poll_count,
            )

        self._failed_poll_count = 0
        self._cached_params.update(self._without_transient_bad_values(current_params))

    def _without_transient_bad_values(
        self, current_params: dict[str, Any]
    ) -> dict[str, Any]:
        """Filter transient cloud values that should not replace cached state."""
        params = current_params.copy()
        cached_ambient = self._cached_params.get(AC_TEMPERATURE_AMBIENT)
        if params.get(AC_TEMPERATURE_AMBIENT) == 0 and cached_ambient not in (None, 0):
            _LOGGER.debug(
                "Ignoring transient zero ambient temperature; keeping cached value %s",
                cached_ambient,
            )
            params.pop(AC_TEMPERATURE_AMBIENT)
        return params


class BaseEntity(CoordinatorEntity["AuxCloudCoordinator"]):
    """Base class for all AUX Cloud entities."""

    def __init__(self, coordinator: Any, device_id: str, entity_description: Any):
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = self.coordinator.get_device_by_endpoint_id(self._device_id) or {}
        self._attr_has_entity_name = True
        self.entity_description = entity_description
        entity_domain = self.__class__.__module__.rsplit(".", maxsplit=1)[-1]
        self._attr_unique_id = collision_safe_entity_unique_id(
            coordinator.hass,
            entity_domain,
            self._device_id,
            self.entity_description.key,
            coordinator._reserved_entity_unique_ids,
            config_entry_id=coordinator._entity_config_entry_id,
            identity_salt=coordinator._entity_unique_id_salt,
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
            identifiers={device_identifier(str(self._device_id))},
            name=str(self._device.get("friendlyName", "AUX")),
            manufacturer=MANUFACTURER,
            model=str(AuxProducts.get_device_name(self._device.get("productId", None))),
        )

        if self._device.get("mac"):
            with contextlib.suppress(ValueError):
                info["connections"] = {
                    (CONNECTION_NETWORK_MAC, format_mac(str(self._device["mac"])))
                }

        return info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self._device is not None
            and self._device.get("endpointId") is not None
            and self._device.get("state", 1) != 0
            and self._state_helper.is_available()
        )

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        device_from_coordinator = self.coordinator.get_device_by_endpoint_id(
            self._device_id
        )
        self._device = device_from_coordinator or {}

        raw_params = self._device.get("params", {})
        device_name = self._device.get("friendlyName", self._device_id)

        # Helper is now the source of truth for params
        self._state_helper.process_new_payload(
            raw_params,
            device_name,
            update_id=self.coordinator.update_generation,
        )

        self.async_write_ha_state()

    def _get_device_params(self) -> dict[str, Any]:
        """Get device parameters securely from the state helper."""
        return self._state_helper.current_params

    async def _set_device_params(self, params: dict[str, Any]):
        """Delegate the serialized optimistic transaction to the coordinator."""
        try:
            await self.coordinator.async_set_device_params(self._device, params)
        except AuxApiError as err:
            raise HomeAssistantError(
                str(err),
                translation_domain=DOMAIN,
                translation_key=err.translation_key,
                translation_placeholders={"error": str(err)},
            ) from err


def setup_dynamic_entities(
    entry: ConfigEntry,
    coordinator: Any,
    async_add_entities: Callable[[list[Any], bool], None],
    entity_factory: Callable[[dict[str, Any]], Iterable[Any]],
) -> None:
    """Add initial and newly discovered entities without duplicating unique IDs."""
    known_unique_ids: set[str] = set()

    @callback
    def add_devices(devices: list[dict[str, Any]]) -> None:
        entities = []
        for device in devices:
            for entity in entity_factory(device):
                if entity.unique_id in known_unique_ids:
                    continue
                known_unique_ids.add(entity.unique_id)
                entities.append(entity)
        if entities:
            async_add_entities(entities, True)

    add_devices((coordinator.data or {"devices": []})["devices"])
    entry.async_on_unload(coordinator.async_add_device_listener(add_devices))
