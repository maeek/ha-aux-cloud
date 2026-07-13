"""Regression tests for account-scoped device state transitions."""

from custom_components.aux_cloud.api.models import DeviceUpdate
from custom_components.aux_cloud.state import AccountState


def _store() -> AccountState:
    store = AccountState(lambda _device: None)
    store.reconcile(
        [
            {
                "endpointId": "device1",
                "state": 1,
                "params": {"pwr": 0, "temp": 20},
            }
        ],
        complete=True,
        scan_revision=0,
    )
    return store


def test_identical_push_is_a_semantic_noop():
    """An identical relay update must not churn timestamps or listeners."""
    store = _store()

    assert not store.apply_updates((DeviceUpdate("device1", {"pwr": 0}),))
    assert not store.apply_updates((DeviceUpdate("missing", {"pwr": 1}),))


def test_push_supersedes_only_matching_optimistic_keys():
    """A command ACK or rollback cannot overwrite a newer pushed key."""
    store = _store()
    token = store.begin_command("device1", {"pwr": 1, "new": 1})

    assert token is not None and token.changed
    assert store.apply_updates((DeviceUpdate("device1", {"pwr": 2}),))
    assert store.confirm_command(token, {"pwr": 1, "new": 1}) is False
    assert store.get("device1")["params"] == {"pwr": 2, "temp": 20, "new": 1}

    rollback = store.begin_command("device1", {"pwr": 3, "new": 2})
    assert rollback is not None
    assert store.apply_updates((DeviceUpdate("device1", {"pwr": 4}),))
    assert store.rollback_command(rollback)
    assert store.get("device1")["params"] == {"pwr": 4, "temp": 20, "new": 1}


def test_scan_preserves_fields_changed_after_it_started():
    """A slow HTTP scan cannot replace a newer relay update."""
    store = _store()
    scan_revision = store.revision
    assert store.apply_updates((DeviceUpdate("device1", {"pwr": 1}),))

    delta = store.reconcile(
        [
            {
                "endpointId": "device1",
                "state": 1,
                "params": {"pwr": 0, "temp": 21},
            }
        ],
        complete=True,
        scan_revision=scan_revision,
    )

    assert not delta.added
    assert not delta.removed
    assert store.get("device1")["params"] == {"pwr": 1, "temp": 21}


def test_registry_only_device_requires_two_complete_absences():
    """A device removed while HA was stopped is eventually removed from registry."""
    store = AccountState(lambda _device: None)

    first = store.reconcile(
        [], complete=True, scan_revision=0, registry_ids={"offline-device"}
    )
    second = store.reconcile(
        [], complete=True, scan_revision=0, registry_ids={"offline-device"}
    )

    assert not first.removed
    assert second.removed == {"offline-device"}


def test_command_noop_tracks_races_without_publishing():
    """An unchanged optimistic value gets a CAS token without state churn."""
    store = _store()

    token = store.begin_command("device1", {"pwr": 0})

    assert token is not None and not token.changed
