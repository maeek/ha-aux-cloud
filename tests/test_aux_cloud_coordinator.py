"""Test AUX Cloud coordinator functionality."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.aux_cloud.coordinator as coordinator_module
from custom_components.aux_cloud import FALLBACK_SCAN_INTERVAL, AuxCloudCoordinator
from custom_components.aux_cloud.api.errors import (
    AuxAuthError,
    AuxRateLimitError,
    AuxServerError,
)
from custom_components.aux_cloud.api.models import AuxCredentials, DeviceUpdate
from custom_components.aux_cloud.api.protocol.websocket import extract_websocket_updates
from custom_components.aux_cloud.const import (
    CONF_PHONE_NUMBER,
    DOMAIN,
)
from custom_components.aux_cloud.coordinator import TOPOLOGY_SCAN_INTERVAL
from custom_components.aux_cloud.devices.profiles import AC_TEMPERATURE_AMBIENT
from custom_components.aux_cloud.entity import BaseEntity

# This enables all the Home Assistant pytest fixtures
pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def mock_aux_cloud_api():
    """Create a mock AuxCloudAPI instance."""
    api = MagicMock()
    api.is_logged_in = MagicMock(return_value=True)
    api.login = AsyncMock(return_value=True)
    api.get_families = AsyncMock(
        return_value=[{"familyid": "family1", "name": "Family 1"}]
    )

    # Make get_devices return different results based on the 'shared' parameter
    async def mock_get_devices(familyid, shared=False):
        if shared:
            return []  # No shared devices
        else:
            return [
                {
                    "endpointId": "device1",
                    "friendlyName": "AC Unit 1",
                    "productId": "000000000000000000000000c0620000",
                    "state": 1,
                    "params": {"pwr": 1},
                }
            ]

    api.get_devices = AsyncMock(side_effect=mock_get_devices)
    api.async_run_websocket = AsyncMock()
    api.close_websocket = AsyncMock()
    api.async_update_websocket_subscriptions = AsyncMock()
    api.normalize_device_params = MagicMock()
    api.set_device_params = AsyncMock(return_value={"pwr": 1})
    api.user_id = None
    return api


@pytest.fixture
def config_entry(hass):
    """Create a config entry containing canonical account credentials."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "password123",
            CONF_REGION: "eu",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def coordinator(hass, mock_aux_cloud_api, config_entry):
    """Create an AuxCloudCoordinator instance."""
    return AuxCloudCoordinator(
        hass=hass,
        api=mock_aux_cloud_api,
        config_entry=config_entry,
    )


def _seed_coordinator(coordinator, devices) -> None:
    """Seed coordinator state through the production reconciliation boundary."""
    coordinator._state.reconcile(
        devices,
        complete=True,
        scan_revision=coordinator._state.revision,
    )
    coordinator._publish_devices()


async def test_coordinator_update_deduplicates_shared_devices(
    coordinator, mock_aux_cloud_api
):
    """Test refresh keeps one entity source per physical device."""
    mock_aux_cloud_api.get_devices.side_effect = [
        [
            {
                "endpointId": "device1",
                "friendlyName": "AC Unit 1",
                "productId": "000000000000000000000000c0620000",
                "state": 1,
                "params": {"pwr": 1},
            }
        ],
        [
            {
                "endpointId": "device1",
                "friendlyName": "AC Unit 1 Shared",
                "productId": "000000000000000000000000c0620000",
                "state": 1,
                "params": {"pwr": 0},
            }
        ],
    ]

    data = await coordinator._async_update_data()

    assert data == {
        "device1": {
            "endpointId": "device1",
            "friendlyName": "AC Unit 1",
            "productId": "000000000000000000000000c0620000",
            "state": 1,
            "params": {"pwr": 1},
        }
    }


async def test_coordinator_update_phone_login(hass, mock_aux_cloud_api):
    """Test coordinator re-login uses phone credentials for phone entries."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_PHONE_NUMBER: "13800138000",
            CONF_PASSWORD: "password123",
            CONF_REGION: "eu",
        },
    )
    entry.add_to_hass(hass)
    coordinator = AuxCloudCoordinator(
        hass=hass,
        api=mock_aux_cloud_api,
        config_entry=entry,
    )
    mock_aux_cloud_api.is_logged_in.return_value = False

    await coordinator._async_update_data()

    mock_aux_cloud_api.login.assert_awaited_once_with(
        AuxCredentials.phone("13800138000", "password123")
    )


async def test_coordinator_update_login_failure(coordinator, mock_aux_cloud_api):
    """Test coordinator update when login fails."""
    # Simulate not logged in and login failure
    mock_aux_cloud_api.is_logged_in.return_value = False
    mock_aux_cloud_api.login.side_effect = AuxAuthError(code=-1006)

    # Update should fail with Home Assistant's auth-specific setup/update error
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    mock_aux_cloud_api.login.assert_called_once()


async def test_coordinator_update_with_exception(coordinator, mock_aux_cloud_api):
    """Test unexpected implementation errors retain their traceback and type."""
    mock_aux_cloud_api.get_devices.side_effect = RuntimeError("API error")

    with pytest.raises(RuntimeError, match="API error"):
        await coordinator._async_update_data()
    mock_aux_cloud_api.get_devices.assert_called()


async def test_coordinator_preserves_rate_limit_backoff(
    coordinator, mock_aux_cloud_api, monkeypatch
):
    """Test the coordinator passes sanitized cloud backoff to Home Assistant."""

    class RetryAwareUpdateFailed(Exception):
        def __init__(self, message, *, retry_after=None):
            super().__init__(message)
            self.retry_after = retry_after

    monkeypatch.setattr(coordinator_module, "UpdateFailed", RetryAwareUpdateFailed)
    mock_aux_cloud_api.get_devices.side_effect = AuxRateLimitError(retry_after=120)

    with pytest.raises(RetryAwareUpdateFailed) as err:
        await coordinator._async_update_data()

    assert err.value.retry_after == 120


async def test_coordinator_partial_typed_query_error_keeps_devices(
    coordinator, mock_aux_cloud_api
):
    """Test one failed family/shared query does not fail a usable refresh."""
    mock_aux_cloud_api.get_devices.side_effect = [
        [
            {
                "endpointId": "device1",
                "friendlyName": "AC Unit 1",
                "productId": "000000000000000000000000c0620000",
                "state": 1,
                "params": {"pwr": 1},
            }
        ],
        AuxServerError(http_status=503),
    ]

    data = await coordinator._async_update_data()

    assert data["device1"]["endpointId"] == "device1"


async def test_coordinator_auth_error_starts_reauth(coordinator, mock_aux_cloud_api):
    """Test authentication failures surface ConfigEntryAuthFailed."""
    mock_aux_cloud_api.get_devices.side_effect = AuxAuthError(code=-1006)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


def test_coordinator_query_collection_reraises_cancellation(coordinator):
    """Test cancellation is not treated as a recoverable partial query failure."""
    with pytest.raises(asyncio.CancelledError):
        coordinator._collect_device_results(
            [[{"endpointId": "device1"}], asyncio.CancelledError()]
        )


def test_coordinator_retires_params_after_six_empty_complete_scans(coordinator):
    """Test transient empty snapshots retain state through the configured grace."""
    _seed_coordinator(
        coordinator, [{"endpointId": "device1", "state": 1, "params": {"pwr": 1}}]
    )
    empty_snapshot = {"endpointId": "device1", "state": 1, "params": {}}

    for _ in range(5):
        coordinator._state.reconcile(
            [empty_snapshot],
            complete=True,
            scan_revision=coordinator._state.revision,
        )
        assert coordinator._state.get("device1")["params"] == {"pwr": 1}

    coordinator._state.reconcile(
        [empty_snapshot],
        complete=True,
        scan_revision=coordinator._state.revision,
    )

    assert coordinator._state.get("device1")["params"] == {}


def test_coordinator_merges_partial_params_and_ignores_zero_ambient(coordinator):
    """Test valid partial snapshots reset failures without replacing good ambient data."""
    _seed_coordinator(
        coordinator,
        [
            {
                "endpointId": "device1",
                "state": 1,
                "params": {AC_TEMPERATURE_AMBIENT: 215, "pwr": 1},
            }
        ],
    )

    coordinator._state.reconcile(
        [
            {
                "endpointId": "device1",
                "state": 1,
                "params": {AC_TEMPERATURE_AMBIENT: 0, "pwr": 0},
            }
        ],
        complete=True,
        scan_revision=coordinator._state.revision,
    )
    device = coordinator._state.get("device1")

    assert device["params"][AC_TEMPERATURE_AMBIENT] == 215
    assert device["params"]["pwr"] == 0


async def test_coordinator_merges_websocket_updates(coordinator, mock_aux_cloud_api):
    """Test websocket updates merge into coordinator state."""
    _seed_coordinator(
        coordinator,
        [
            {
                "endpointId": "device1",
                "friendlyName": "AC Unit 1",
                "params": {"pwr": 0},
            }
        ],
    )
    original_publish = coordinator._publish_devices
    coordinator._publish_devices = MagicMock(side_effect=original_publish)
    coordinator._handle_websocket_updates(
        extract_websocket_updates(
            {
                "msgtype": "subresetk",
                "data": {
                    "devList": [
                        {
                            "endpointId": "device1",
                            "data": {"did": "device1", "pid": "pid1", "pwr": 1},
                        }
                    ]
                },
            }
        )
    )

    device = coordinator.get_device_by_endpoint_id("device1")
    assert device["params"] == {"pwr": 1}
    coordinator._publish_devices.assert_called_once()


def test_inventory_removes_only_after_two_complete_scans(coordinator):
    """Test partial or one-off empty scans cannot delete a cloud device."""
    device = {"endpointId": "device1", "params": {"pwr": 1}}
    _seed_coordinator(coordinator, [device])

    for complete, expected in ((False, True), (True, True), (True, False)):
        coordinator._state.reconcile(
            [], complete=complete, scan_revision=coordinator._state.revision
        )
        assert (coordinator._state.get("device1") is not None) is expected


def test_confirmed_stale_device_is_removed_from_registry(coordinator):
    """Test confirmed cloud removal also cleans the HA device registry."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, entry_id="entry1")
    entry.add_to_hass(coordinator.hass)
    coordinator.config_entry = entry
    registry = dr.async_get(coordinator.hass)
    registry.async_get_or_create(
        config_entry_id="entry1",
        identifiers={(DOMAIN, "device1")},
    )

    coordinator._async_remove_stale_devices({"device1"})

    device = registry.async_get_device(identifiers={(DOMAIN, "device1")})
    assert device is None or "entry1" not in device.config_entries


async def test_coordinator_marks_websocket_offline_update_unavailable(
    coordinator, mock_aux_cloud_api
):
    """Test websocket stale params are ignored when payload says device is offline."""
    _seed_coordinator(
        coordinator,
        [
            {
                "endpointId": "device1",
                "friendlyName": "AC Unit 1",
                "productId": "000000000000000000000000c0620000",
                "state": 1,
                "params": {"pwr": 1, "temp": 245},
            }
        ],
    )
    entity = BaseEntity(coordinator, "device1", SimpleNamespace(key="pwr"))
    entity.async_write_ha_state = MagicMock()
    assert entity.available is True

    coordinator._handle_websocket_updates(
        extract_websocket_updates(
            {
                "msgtype": "subresetk",
                "data": {
                    "devList": [
                        {
                            "endpointId": "device1",
                            "status": 0,
                            "data": {
                                "online": False,
                                "state": 0,
                                "pwr": 1,
                                "temp": 245,
                            },
                        }
                    ]
                },
            }
        )
    )
    entity._handle_coordinator_update()

    device = coordinator.get_device_by_endpoint_id("device1")
    assert device["state"] == 0
    assert device["params"] == {}
    assert entity.available is False
    assert entity._get_device_params() == {}
    mock_aux_cloud_api.normalize_device_params.assert_not_called()


async def test_coordinator_starts_single_websocket_runner(
    coordinator, mock_aux_cloud_api
):
    """Test coordinator owns a single websocket runner task."""
    started = asyncio.Event()

    async def run_websocket(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    mock_aux_cloud_api.async_run_websocket.side_effect = run_websocket
    coordinator.async_request_refresh = AsyncMock()

    coordinator.start_realtime()
    first_task = coordinator._websocket_task
    await asyncio.wait_for(started.wait(), timeout=1)
    coordinator.start_realtime()

    assert first_task is coordinator._websocket_task
    mock_aux_cloud_api.async_run_websocket.assert_awaited_once()
    await coordinator.async_close()
    assert coordinator._websocket_task is None


async def test_coordinator_retries_websocket_setup_failure(
    coordinator, mock_aux_cloud_api, monkeypatch
):
    """Test setup failure enables fallback polling and retries in one runner task."""
    monkeypatch.setattr(
        coordinator_module,
        "WEBSOCKET_SETUP_RETRY_INITIAL_DELAY",
        0,
    )
    started = asyncio.Event()
    attempts = 0

    async def run_after_failure(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise Exception("relay unavailable")
        started.set()
        await asyncio.Event().wait()

    mock_aux_cloud_api.async_run_websocket.side_effect = run_after_failure
    coordinator.async_request_refresh = AsyncMock()

    coordinator.start_realtime()
    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.sleep(0)

    assert coordinator.update_interval == FALLBACK_SCAN_INTERVAL
    assert mock_aux_cloud_api.async_run_websocket.await_count == 2
    coordinator.async_request_refresh.assert_awaited_once()
    await coordinator.async_close()


async def test_websocket_backoff_resets_immediately_after_ready(
    coordinator, mock_aux_cloud_api, monkeypatch
):
    """Test an established connection never inherits an old maximum backoff."""
    attempts = 0
    sleeps = []

    async def run_websocket(*_args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            kwargs["on_ready"]()
        raise AuxServerError()

    async def capture_sleep(delay):
        sleeps.append(delay)
        if len(sleeps) == 2:
            raise asyncio.CancelledError

    mock_aux_cloud_api.async_run_websocket.side_effect = run_websocket
    coordinator.async_request_refresh = AsyncMock()
    monkeypatch.setattr(coordinator_module.random, "uniform", lambda *_args: 1)
    monkeypatch.setattr(coordinator_module.asyncio, "sleep", capture_sleep)

    with pytest.raises(asyncio.CancelledError):
        await coordinator._run_websocket()

    assert sleeps == [5, 5]


async def test_websocket_rate_limit_is_a_retry_floor(
    coordinator, mock_aux_cloud_api, monkeypatch
):
    """Test relay rate limits are never retried earlier than requested."""
    mock_aux_cloud_api.async_run_websocket.side_effect = AuxRateLimitError(
        retry_after=30
    )
    coordinator.async_request_refresh = AsyncMock()
    monkeypatch.setattr(coordinator_module.random, "uniform", lambda *_args: 1)
    original_sleep = asyncio.sleep

    async def cancel_after_delay(delay):
        if delay == 0:
            await original_sleep(0)
            return
        assert delay == 30
        raise asyncio.CancelledError

    monkeypatch.setattr(coordinator_module.asyncio, "sleep", cancel_after_delay)

    with pytest.raises(asyncio.CancelledError):
        await coordinator._run_websocket()


async def test_coordinator_switches_polling_with_websocket_health(coordinator):
    """Test degraded sockets enable fallback polling until they recover."""
    coordinator.async_request_refresh = AsyncMock()

    coordinator._set_websocket_connected(False)
    await asyncio.sleep(0)
    coordinator._set_websocket_connected(False)
    await asyncio.sleep(0)

    assert coordinator.update_interval == FALLBACK_SCAN_INTERVAL
    coordinator.async_request_refresh.assert_awaited_once()

    coordinator._set_websocket_connected(True)

    assert coordinator.update_interval == TOPOLOGY_SCAN_INTERVAL
    assert coordinator.websocket_degraded is False


async def test_base_entity_rolls_back_optimistic_update_on_command_failure(
    coordinator, mock_aux_cloud_api
):
    """Test optimistic entity state rolls back when the command fails."""
    _seed_coordinator(
        coordinator,
        [
            {
                "endpointId": "device1",
                "friendlyName": "AC Unit 1",
                "productId": "000000000000000000000000c0620000",
                "params": {"pwr": 0},
            }
        ],
    )
    entity = BaseEntity(coordinator, "device1", SimpleNamespace(key="pwr"))
    entity.async_write_ha_state = MagicMock()
    mock_aux_cloud_api.set_device_params.side_effect = Exception("command failed")

    with pytest.raises(Exception, match="command failed"):
        await entity._set_device_params({"pwr": 1, "new_key": 1})

    assert entity._get_device_params()["pwr"] == 0
    assert "new_key" not in entity._get_device_params()


def test_push_publication_does_not_reset_topology_poll(coordinator):
    """Test continuous relay traffic cannot starve inventory discovery."""
    _seed_coordinator(coordinator, [{"endpointId": "device1", "params": {"pwr": 0}}])
    coordinator._async_unsub_refresh = MagicMock()

    coordinator._handle_websocket_updates((DeviceUpdate("device1", {"pwr": 1}),))

    coordinator._async_unsub_refresh.assert_not_called()


async def test_cancelled_command_rolls_back_only_unsuperseded_keys(
    coordinator, mock_aux_cloud_api
):
    """Test cancellation keeps a pushed key while removing optimistic-only state."""
    _seed_coordinator(
        coordinator, [{"endpointId": "device1", "state": 1, "params": {"pwr": 0}}]
    )
    started = asyncio.Event()

    async def wait_for_cancel(_device, _params):
        started.set()
        await asyncio.Event().wait()

    mock_aux_cloud_api.set_device_params.side_effect = wait_for_cancel
    command = asyncio.create_task(
        coordinator.async_set_device_params("device1", {"pwr": 1, "new": 1})
    )
    await started.wait()
    coordinator._handle_websocket_updates((DeviceUpdate("device1", {"pwr": 2}),))
    command.cancel()

    with pytest.raises(asyncio.CancelledError):
        await command
    assert coordinator.get_device_by_endpoint_id("device1")["params"] == {"pwr": 2}
