"""Account-scoped AUX device state transitions."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, cast

from .api.models import AuxDevice, DeviceUpdate
from .const import MAX_FAILED_POLLS
from .devices import AC_TEMPERATURE_AMBIENT

_AVAILABILITY = "__availability__"
_MISSING = object()
_STALE_PUSH_WINDOW_SECONDS = 10.0

type CoordinatorData = dict[str, AuxDevice]


@dataclass(frozen=True, slots=True)
class InventoryDelta:
    """Membership changes produced by an inventory reconciliation."""

    added: frozenset[str]
    removed: frozenset[str]


@dataclass(frozen=True, slots=True)
class CommandToken:
    """Compare-and-swap token for one optimistic command."""

    endpoint_id: str
    revision: int
    previous: Mapping[str, object]
    changed: bool


@dataclass(slots=True)
class _PendingWrite:
    """Latest requested value and recent values it superseded."""

    expected: object
    superseded: tuple[tuple[object, float], ...]
    revision: int
    expires_at: float


@dataclass(slots=True)
class _DeviceTracking:
    """Transient reconciliation state for one device."""

    missing_complete_scans: int = 0
    empty_param_scans: int = 0
    pending_writes: dict[str, _PendingWrite] = field(default_factory=dict)


class AccountState:
    """Own non-persistent device reconciliation state for one account session."""

    def __init__(self, normalizer: Callable[[AuxDevice], None]) -> None:
        """Initialize an empty account state store."""
        self._normalizer = normalizer
        self._devices: CoordinatorData = {}
        self._tracking: dict[str, _DeviceTracking] = {}
        self._field_revisions: dict[str, dict[str, int]] = {}
        self._revision = 0

    @property
    def revision(self) -> int:
        """Return the current semantic state revision."""
        return self._revision

    @property
    def data(self) -> CoordinatorData:
        """Return a shallow copy of the current keyed snapshot."""
        return dict(self._devices)

    @property
    def devices(self) -> list[AuxDevice]:
        """Return devices in stable discovery order for the public API."""
        return list(self._devices.values())

    def get(self, endpoint_id: str) -> AuxDevice | None:
        """Return a device by endpoint ID."""
        return self._devices.get(endpoint_id)

    def apply_updates(self, updates: Iterable[DeviceUpdate]) -> bool:
        """Apply validated push updates, skipping semantic no-ops."""
        changed = False
        for update in updates:
            changed = self._apply_update(update) or changed
        return changed

    def _apply_update(self, update: DeviceUpdate) -> bool:
        """Apply one push update and report a semantic change."""
        current = self._devices.get(update.endpoint_id)
        if current is None:
            return False
        tracking = self._tracking.setdefault(update.endpoint_id, _DeviceTracking())
        if update.available is False:
            tracking.pending_writes.clear()
            candidate, fields = self._offline_update(current)
        else:
            candidate, fields = self._online_update(current, update, tracking)
        if not fields or current == candidate:
            return False
        self._commit(update.endpoint_id, candidate, fields)
        tracking.empty_param_scans = 0
        return True

    @staticmethod
    def _offline_update(current: AuxDevice) -> tuple[AuxDevice, set[str]]:
        """Build an explicit offline snapshot."""
        if current.get("state") == 0 and not current.get("params"):
            return current, set()
        candidate = _copy_device(current)
        candidate["state"] = 0
        candidate["params"] = {}
        return candidate, {_AVAILABILITY, *current.get("params", {})}

    def _online_update(
        self,
        current: AuxDevice,
        update: DeviceUpdate,
        tracking: _DeviceTracking,
    ) -> tuple[AuxDevice, set[str]]:
        """Build a merged online snapshot and its changed fields."""
        candidate = _copy_device(current)
        cleaned = self._filter_stale_push_values(
            {
                key: value
                for key, value in update.params.items()
                if key not in {"did", "pid"}
            },
            tracking.pending_writes,
        )
        previous = current.get("params", {})
        merged = _merge_params(previous, cleaned)
        fields = {
            key for key, value in merged.items() if previous.get(key, _MISSING) != value
        }
        if update.available is True and candidate.get("state") != 1:
            candidate["state"] = 1
            fields.add(_AVAILABILITY)
        if fields:
            candidate["params"] = merged
            self._normalizer(candidate)
        return candidate, fields

    @staticmethod
    def _filter_stale_push_values(
        values: Mapping[str, Any], pending_writes: dict[str, _PendingWrite]
    ) -> dict[str, Any]:
        """Drop only recent push values superseded by a newer command."""
        now = monotonic()
        accepted: dict[str, Any] = {}
        for key, value in values.items():
            pending = pending_writes.get(key)
            if pending is None:
                accepted[key] = value
                continue
            if now >= pending.expires_at:
                pending_writes.pop(key)
                accepted[key] = value
                continue
            if value == pending.expected:
                pending_writes.pop(key)
                accepted[key] = value
                continue
            if any(
                now < expires_at and value == superseded
                for superseded, expires_at in pending.superseded
            ):
                continue
            accepted[key] = value
        return accepted

    def begin_command(
        self, endpoint_id: str, values: Mapping[str, Any]
    ) -> CommandToken | None:
        """Apply optimistic values and return a key-scoped rollback token."""
        current = self._devices.get(endpoint_id)
        if current is None:
            return None
        previous_params = current.get("params", {})
        previous = {key: previous_params.get(key, _MISSING) for key in values}
        candidate = _copy_device(current)
        candidate["params"] = {**previous_params, **values}
        self._normalizer(candidate)
        changed = current != candidate
        revision = self._next_revision()
        self._devices[endpoint_id] = candidate
        field_revisions = self._field_revisions.setdefault(endpoint_id, {})
        pending_writes = self._tracking.setdefault(
            endpoint_id, _DeviceTracking()
        ).pending_writes
        now = monotonic()
        for key, value in values.items():
            field_revisions[key] = revision
            previous_pending = pending_writes.get(key)
            superseded = []
            if previous_pending is not None and now < previous_pending.expires_at:
                superseded = [
                    item
                    for item in previous_pending.superseded
                    if now < item[1] and item[0] != value
                ]
                if previous_pending.expected != value:
                    superseded = [
                        item
                        for item in superseded
                        if item[0] != previous_pending.expected
                    ]
                    superseded.append(
                        (previous_pending.expected, previous_pending.expires_at)
                    )
            pending_writes[key] = _PendingWrite(
                expected=value,
                superseded=tuple(superseded),
                revision=revision,
                expires_at=now + _STALE_PUSH_WINDOW_SECONDS,
            )
        return CommandToken(endpoint_id, revision, previous, changed)

    def confirm_command(
        self, token: CommandToken, confirmed: Mapping[str, Any]
    ) -> bool:
        """Confirm keys that have not been superseded since the command began."""
        changed = self._finish_command(token, confirmed, rollback=False)
        tracking = self._tracking.get(token.endpoint_id)
        if tracking is not None:
            expires_at = monotonic() + _STALE_PUSH_WINDOW_SECONDS
            for key in token.previous:
                pending = tracking.pending_writes.get(key)
                if pending is not None and pending.revision == token.revision:
                    pending.expires_at = expires_at
        return changed

    def rollback_command(self, token: CommandToken) -> bool:
        """Restore optimistic keys that have not been superseded by a push."""
        changed = self._finish_command(token, token.previous, rollback=True)
        tracking = self._tracking.get(token.endpoint_id)
        if tracking is not None:
            for key in token.previous:
                pending = tracking.pending_writes.get(key)
                if pending is not None and pending.revision == token.revision:
                    tracking.pending_writes.pop(key)
        return changed

    def reconcile(
        self,
        discovered: Iterable[AuxDevice],
        *,
        complete: bool,
        scan_revision: int,
        registry_ids: Iterable[str] = (),
    ) -> InventoryDelta:
        """Merge one scan without overwriting newer push or command fields."""
        previous_ids = set(self._devices)
        discovered_by_id = {
            endpoint_id: _copy_device(device)
            for device in discovered
            if (endpoint_id := device.get("endpointId"))
        }
        next_devices: CoordinatorData = {}

        for endpoint_id, incoming in discovered_by_id.items():
            tracking = self._tracking.setdefault(endpoint_id, _DeviceTracking())
            tracking.missing_complete_scans = 0
            next_devices[endpoint_id] = self._reconcile_device(
                endpoint_id, incoming, complete=complete, scan_revision=scan_revision
            )

        missing_ids = (previous_ids | set(registry_ids)) - set(discovered_by_id)
        removed: set[str] = set()
        for endpoint_id in missing_ids:
            tracking = self._tracking.setdefault(endpoint_id, _DeviceTracking())
            if complete:
                tracking.missing_complete_scans += 1
            if not complete or tracking.missing_complete_scans < 2:
                if old_device := self._devices.get(endpoint_id):
                    next_devices[endpoint_id] = old_device
                continue
            removed.add(endpoint_id)
            self._tracking.pop(endpoint_id, None)
            self._field_revisions.pop(endpoint_id, None)

        changed = self._devices != next_devices
        self._devices = next_devices
        if changed:
            self._next_revision()
        current_ids = set(next_devices)
        return InventoryDelta(
            added=frozenset(current_ids - previous_ids),
            removed=frozenset(removed | (previous_ids - current_ids)),
        )

    def _reconcile_device(
        self,
        endpoint_id: str,
        incoming: AuxDevice,
        *,
        complete: bool,
        scan_revision: int,
    ) -> AuxDevice:
        """Reconcile one scan record against the latest state."""
        current = self._devices.get(endpoint_id)
        if current is None:
            if incoming.get("params"):
                self._normalizer(incoming)
            return incoming

        tracking = self._tracking[endpoint_id]
        field_revisions = self._field_revisions.get(endpoint_id, {})
        availability_changed = field_revisions.get(_AVAILABILITY, 0) > scan_revision
        incoming_params = incoming.get("params", {})

        if incoming.get("state") == 0 and not availability_changed:
            tracking.empty_param_scans = 0
            tracking.pending_writes.clear()
            candidate = cast(AuxDevice, {**incoming, "params": {}})
        elif incoming_params:
            candidate = self._merge_scan_params(
                current,
                incoming,
                field_revisions=field_revisions,
                scan_revision=scan_revision,
                availability_changed=availability_changed,
            )
            tracking.empty_param_scans = 0
        else:
            candidate = self._empty_scan_snapshot(
                current,
                incoming,
                tracking=tracking,
                complete=complete,
                availability_changed=availability_changed,
            )

        if current == candidate:
            return current
        return candidate

    def _merge_scan_params(
        self,
        current: AuxDevice,
        incoming: AuxDevice,
        *,
        field_revisions: Mapping[str, int],
        scan_revision: int,
        availability_changed: bool,
    ) -> AuxDevice:
        """Merge scan params while preserving fields changed after scan start."""
        current_params = current.get("params", {})
        merged = _merge_params(current_params, incoming.get("params", {}))
        for key, value in current_params.items():
            if field_revisions.get(key, 0) > scan_revision:
                merged[key] = value
        candidate: AuxDevice = {**incoming, "params": merged}
        if availability_changed:
            candidate["state"] = current.get("state", 1)
        self._normalizer(candidate)
        return candidate

    @staticmethod
    def _empty_scan_snapshot(
        current: AuxDevice,
        incoming: AuxDevice,
        *,
        tracking: _DeviceTracking,
        complete: bool,
        availability_changed: bool,
    ) -> AuxDevice:
        """Retain safe params across bounded empty authoritative scans."""
        if complete:
            tracking.empty_param_scans += 1
        current_params = current.get("params", {})
        retain = bool(current_params) and (
            not complete or tracking.empty_param_scans <= MAX_FAILED_POLLS
        )
        candidate: AuxDevice = {
            **incoming,
            "params": dict(current_params) if retain else {},
        }
        if availability_changed:
            candidate["state"] = current.get("state", 1)
        return candidate

    def _finish_command(
        self,
        token: CommandToken,
        values: Mapping[str, object],
        *,
        rollback: bool,
    ) -> bool:
        current = self._devices.get(token.endpoint_id)
        if current is None:
            return False
        revisions = self._field_revisions.get(token.endpoint_id, {})
        params = dict(current.get("params", {}))
        changed_keys: set[str] = set()
        for key, value in values.items():
            if revisions.get(key) != token.revision:
                continue
            if rollback and value is _MISSING:
                if key in params:
                    params.pop(key)
                    changed_keys.add(key)
                continue
            if params.get(key, _MISSING) != value:
                params[key] = value
                changed_keys.add(key)
        if not changed_keys:
            return False
        candidate = _copy_device(current)
        candidate["params"] = params
        self._normalizer(candidate)
        self._commit(token.endpoint_id, candidate, changed_keys)
        return True

    def _commit(
        self, endpoint_id: str, candidate: AuxDevice, fields: Iterable[str]
    ) -> None:
        revision = self._next_revision()
        self._devices[endpoint_id] = candidate
        field_revisions = self._field_revisions.setdefault(endpoint_id, {})
        for key in fields:
            field_revisions[key] = revision

    def _next_revision(self) -> int:
        self._revision += 1
        return self._revision


def _copy_device(device: AuxDevice) -> AuxDevice:
    return {**device, "params": dict(device.get("params", {}))}


def _merge_params(
    previous: Mapping[str, Any], incoming: Mapping[str, Any]
) -> dict[str, Any]:
    cleaned = dict(incoming)
    previous_ambient = previous.get(AC_TEMPERATURE_AMBIENT)
    if cleaned.get(AC_TEMPERATURE_AMBIENT) == 0 and previous_ambient not in (None, 0):
        cleaned.pop(AC_TEMPERATURE_AMBIENT)
    return {**previous, **cleaned}
