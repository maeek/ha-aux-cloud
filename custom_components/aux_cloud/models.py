"""Typed data models used by the AUX Cloud integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict

from homeassistant.config_entries import ConfigEntry


class AuxDevice(TypedDict, total=False):
    """Cloud device record normalized for Home Assistant."""

    endpointId: str
    friendlyName: str
    productId: str
    familyId: str
    roomId: str
    gatewayId: str
    devSession: str
    mac: str
    state: int
    params: dict[str, Any]
    last_updated: str


class CoordinatorData(TypedDict):
    """Coordinator state exposed to entity platforms."""

    devices: list[AuxDevice]


class InventoryResult(TypedDict):
    """One topology scan result."""

    devices: list[AuxDevice]
    complete: bool


@dataclass(slots=True)
class AuxCloudRuntimeData:
    """Runtime-only objects associated with a config entry."""

    coordinator: Any
    api: Any


if TYPE_CHECKING:
    AuxCloudConfigEntry = ConfigEntry[AuxCloudRuntimeData]
else:
    # ConfigEntry became generic after the oldest test environment supported by
    # this repository. Keep runtime imports harmless during migration tooling.
    AuxCloudConfigEntry = ConfigEntry
