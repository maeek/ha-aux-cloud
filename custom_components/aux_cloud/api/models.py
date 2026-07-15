"""Cloud-facing data transfer objects for AUX Cloud."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from ..devices import ProductProfile


@dataclass(frozen=True, slots=True)
class AuxCredentials:
    """One normalized AUX Cloud account credential."""

    kind: Literal["email", "phone"]
    username: str
    password: str = field(repr=False)

    @classmethod
    def email(cls, email: str, password: str) -> AuxCredentials:
        """Build normalized email credentials."""
        return cls("email", email.strip().lower(), password)

    @classmethod
    def phone(cls, phone_number: str, password: str) -> AuxCredentials:
        """Build normalized phone credentials."""
        return cls("phone", phone_number, password)


class AuxDevice(TypedDict, total=False):
    """Cloud device record normalized for Home Assistant."""

    endpointId: str
    friendlyName: str
    productId: str
    familyId: str
    roomId: str
    gatewayId: str
    devSession: str
    devicetypeFlag: int
    cookie: str
    extern: str | dict[str, Any]
    mac: str
    state: int
    params: dict[str, Any]
    profile: ProductProfile
    _aux_protocol_version: int
    _aux_query_failures: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class InventorySnapshot:
    """One account inventory scan and whether every cloud query completed."""

    devices: tuple[AuxDevice, ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class DeviceUpdate:
    """One validated relay update for a cloud device."""

    endpoint_id: str
    params: Mapping[str, Any]
    available: bool | None = None
