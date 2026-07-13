"""Shared AUX entity behavior and dynamic platform setup."""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AuxApiError
from .api.models import AuxDevice
from .const import DOMAIN, MANUFACTURER
from .coordinator import AuxCloudCoordinator
from .devices.profiles import get_product_profile
from .identifiers import collision_safe_entity_unique_id, device_identifier


def supported_entity_descriptions[DescriptionT: EntityDescription](
    device: AuxDevice, descriptions: Iterable[DescriptionT]
) -> list[DescriptionT]:
    """Return entity descriptions backed by the device product profile."""
    product_id = device.get("productId")
    if not product_id:
        return []
    profile = get_product_profile(product_id)
    supported_params = {*profile.params, *profile.special_params}
    return [
        description
        for description in descriptions
        if description.key in supported_params
    ]


class BaseEntity(CoordinatorEntity["AuxCloudCoordinator"]):
    """Base class for all AUX Cloud entities."""

    def __init__(
        self,
        coordinator: AuxCloudCoordinator,
        device_id: str,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = self.coordinator.get_device_by_endpoint_id(device_id) or {}
        self._attr_has_entity_name = True
        self.entity_description = entity_description
        entity_domain = self.__class__.__module__.rsplit(".", maxsplit=1)[-1]
        self._attr_unique_id = collision_safe_entity_unique_id(
            coordinator.hass,
            entity_domain,
            device_id,
            entity_description.key,
            coordinator._reserved_entity_unique_ids,
            config_entry_id=coordinator.config_entry.entry_id,
            identity_salt=(
                coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
            ),
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        info = DeviceInfo(
            identifiers={device_identifier(self._device_id)},
            name=str(self._device.get("friendlyName", "AUX")),
            manufacturer=MANUFACTURER,
            model=get_product_profile(self._device.get("productId")).model_name,
        )
        if self._device.get("mac"):
            with contextlib.suppress(ValueError):
                info["connections"] = {
                    (CONNECTION_NETWORK_MAC, format_mac(str(self._device["mac"])))
                }
        return info

    @property
    def available(self) -> bool:
        """Return whether the cloud device has a usable live snapshot."""
        return (
            super().available
            and bool(self._device.get("endpointId"))
            and self._device.get("state", 1) != 0
            and bool(self._device.get("params"))
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh the cached device after coordinator publication."""
        self._device = self.coordinator.get_device_by_endpoint_id(self._device_id) or {}
        self.async_write_ha_state()

    def _get_device_params(self) -> dict[str, Any]:
        """Return parameters from the coordinator snapshot."""
        return self._device.get("params", {})

    async def _set_device_params(self, params: dict[str, Any]) -> None:
        """Delegate an optimistic transaction to the coordinator."""
        try:
            await self.coordinator.async_set_device_params(self._device_id, params)
        except AuxApiError as err:
            raise HomeAssistantError(
                str(err),
                translation_domain=DOMAIN,
                translation_key=err.translation_key,
                translation_placeholders={"error": str(err)},
            ) from err


def setup_dynamic_entities(
    entry: ConfigEntry,
    coordinator: AuxCloudCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    entity_factory: Callable[[AuxDevice], Iterable[Entity]],
) -> None:
    """Add entities after coordinator data publication without duplicates."""
    known_endpoint_ids: set[str] = set()

    @callback
    def sync_devices() -> None:
        current_ids = set(coordinator.data or {})
        known_endpoint_ids.intersection_update(current_ids)
        entities: list[Entity] = []
        for endpoint_id in current_ids - known_endpoint_ids:
            entities.extend(entity_factory(coordinator.data[endpoint_id]))
            known_endpoint_ids.add(endpoint_id)
        if entities:
            async_add_entities(entities)

    sync_devices()
    entry.async_on_unload(coordinator.async_add_listener(sync_devices))
