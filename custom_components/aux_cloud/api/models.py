"""Cloud-facing data transfer objects for AUX Cloud."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
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


@dataclass(frozen=True, slots=True)
class EnergyReading:
    """Energy consumed by a device during one calendar day."""

    day: date
    energy_kwh: float


@dataclass(frozen=True, slots=True)
class EnergyStatistics:
    """Daily energy consumption history the cloud holds for one device."""

    endpoint_id: str
    readings: tuple[EnergyReading, ...]

    @property
    def total_kwh(self) -> float:
        """Return the lifetime consumption known to the cloud."""
        return sum(reading.energy_kwh for reading in self.readings)

    def energy_for_day(self, day: date) -> float:
        """Return the consumption reported for one calendar day."""
        return sum(
            reading.energy_kwh for reading in self.readings if reading.day == day
        )
