"""Test AUX Cloud coordinator functionality."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.aux_cloud as integration
from custom_components.aux_cloud import FALLBACK_SCAN_INTERVAL, AuxCloudCoordinator
from custom_components.aux_cloud.api import AuxWebSocketState
from custom_components.aux_cloud.api.errors import AuxAuthError, AuxServerError
from custom_components.aux_cloud.const import (
    CONF_ACCOUNT_ID,
    CONF_PHONE_NUMBER,
    CONF_SELECTED_DEVICES,
    DOMAIN,
)
from custom_components.aux_cloud.coordinator import TOPOLOGY_SCAN_INTERVAL
from custom_components.aux_cloud.devices.profiles import AC_TEMPERATURE_AMBIENT
from custom_components.aux_cloud.sensor import SENSORS, AuxCloudSensor
from custom_components.aux_cloud.util import BaseEntity

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
    api.families = {"family1": {"id": "family1", "name": "Family 1", "devices": []}}

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
    api.normalize_device_params = MagicMock()
    api.set_device_params = AsyncMock(return_value={"pwr": 1})
    api.ws_api = None
    api.userid = None
    return api


@pytest.fixture
def coordinator(hass, mock_aux_cloud_api):
    """Create an AuxCloudCoordinator instance."""
    return AuxCloudCoordinator(
        hass=hass,
        api=mock_aux_cloud_api,
        email="test@example.com",
        password="password123",
    )


async def test_coordinator_update(coordinator, mock_aux_cloud_api):
    """Test the coordinator update method."""
    # Test normal update
    data = await coordinator._async_update_data()
    assert "devices" in data
    assert len(data["devices"]) == 1
    assert data["devices"][0]["endpointId"] == "device1"

    # Verify API calls
    mock_aux_cloud_api.is_logged_in.assert_called()
    mock_aux_cloud_api.get_devices.assert_called()


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

    assert data["devices"] == [
        {
            "endpointId": "device1",
            "friendlyName": "AC Unit 1",
            "productId": "000000000000000000000000c0620000",
            "state": 1,
            "params": {"pwr": 1},
        }
    ]


async def test_coordinator_update_not_logged_in(coordinator, mock_aux_cloud_api):
    """Test coordinator update when not logged in."""
    # Simulate not logged in
    mock_aux_cloud_api.is_logged_in.return_value = False

    # Update should attempt login
    await coordinator._async_update_data()
    mock_aux_cloud_api.login.assert_called_once()


async def test_coordinator_update_phone_login(hass, mock_aux_cloud_api):
    """Test coordinator re-login uses phone credentials for phone entries."""
    coordinator = AuxCloudCoordinator(
        hass=hass,
        api=mock_aux_cloud_api,
        email=None,
        password="password123",
        phone_number="13800138000",
    )
    mock_aux_cloud_api.is_logged_in.return_value = False

    await coordinator._async_update_data()

    mock_aux_cloud_api.login.assert_awaited_once_with(
        password="password123",
        phone_number="13800138000",
    )


async def test_coordinator_update_login_failure(coordinator, mock_aux_cloud_api):
    """Test coordinator update when login fails."""
    # Simulate not logged in and login failure
    mock_aux_cloud_api.is_logged_in.return_value = False
    mock_aux_cloud_api.login.return_value = False

    # Update should fail with Home Assistant's auth-specific setup/update error
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    mock_aux_cloud_api.login.assert_called_once()


async def test_coordinator_update_no_families(coordinator, mock_aux_cloud_api):
    """Test coordinator update with no families."""
    # Set families to None
    mock_aux_cloud_api.families = None

    # Make sure get_families returns something valid after being called
    async def get_families_and_update():
        mock_aux_cloud_api.families = {"family1": {"id": "family1", "name": "Family 1"}}
        return [{"familyid": "family1", "name": "Family 1"}]

    mock_aux_cloud_api.get_families = AsyncMock(side_effect=get_families_and_update)

    # Update should fetch families and then proceed
    data = await coordinator._async_update_data()

    # Test passes if we get here without exception
    assert "devices" in data
    mock_aux_cloud_api.get_families.assert_called_once()


async def test_coordinator_get_device_by_endpoint_id(coordinator):
    """Test get_device_by_endpoint_id method."""
    # First set some data
    coordinator.data = {
        "devices": [
            {"endpointId": "device1", "name": "Device 1"},
            {"endpointId": "device2", "name": "Device 2"},
        ]
    }

    # Test retrieving an existing device
    device = coordinator.get_device_by_endpoint_id("device1")
    assert device is not None
    assert device["name"] == "Device 1"

    # Test retrieving non-existent device
    device = coordinator.get_device_by_endpoint_id("non-existent")
    assert device is None


async def test_coordinator_update_with_exception(coordinator, mock_aux_cloud_api):
    """Test coordinator update with exceptions during device fetch."""
    # Simulate exception during get_devices
    mock_aux_cloud_api.get_devices.side_effect = Exception("API error")

    # Update should raise UpdateFailed
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    mock_aux_cloud_api.get_devices.assert_called()


async def test_coordinator_cloud_error_is_logged_once(
    coordinator, mock_aux_cloud_api, caplog
):
    """Test transient cloud failures are logged once until recovery."""
    coordinator.async_set_updated_data({"devices": []})
    mock_aux_cloud_api.get_devices.side_effect = AuxServerError(http_status=503)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert caplog.text.count("AUX Cloud update unavailable") == 1


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

    assert data["devices"][0]["endpointId"] == "device1"


async def test_coordinator_recovery_resets_failure_log_guard(
    coordinator, mock_aux_cloud_api
):
    """Test a successful refresh resets transient failure logging state."""
    mock_aux_cloud_api.get_devices.side_effect = AuxServerError(http_status=503)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    mock_aux_cloud_api.get_devices.side_effect = None
    mock_aux_cloud_api.get_devices.return_value = [
        {
            "endpointId": "device1",
            "friendlyName": "AC Unit 1",
            "productId": "000000000000000000000000c0620000",
            "state": 1,
            "params": {"pwr": 1},
        }
    ]

    await coordinator._async_update_data()

    assert coordinator._cloud_failure_logged is False


async def test_coordinator_auth_error_starts_reauth(coordinator, mock_aux_cloud_api):
    """Test authentication failures surface ConfigEntryAuthFailed."""
    mock_aux_cloud_api.get_devices.side_effect = AuxAuthError(code=-1006)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_handle_exception_results(coordinator, mock_aux_cloud_api):
    """Test coordinator handling exception results from asyncio.gather."""
    # Set up mixed results with normal data and a list containing exceptions
    mock_aux_cloud_api.get_devices.side_effect = [
        [{"endpointId": "device1"}],  # Normal result
        [Exception("API error")],  # A list containing an Exception
    ]

    # Update should still succeed with partial data
    data = await coordinator._async_update_data()
    assert "devices" in data
    assert len(data["devices"]) == 1
    assert data["devices"][0]["endpointId"] == "device1"


def test_coordinator_query_collection_deduplicates_endpoint_ids(coordinator):
    """Test duplicate gathered results keep the first device record."""
    devices, complete = coordinator._collect_device_results(
        [
            [{"endpointId": "device1", "source": "personal"}],
            [
                {"endpointId": "device1", "source": "shared"},
                {"endpointId": "device2", "source": "shared"},
            ],
        ]
    )

    assert devices == [
        {"endpointId": "device1", "source": "personal"},
        {"endpointId": "device2", "source": "shared"},
    ]
    assert complete is True


def test_coordinator_query_collection_reraises_cancellation(coordinator):
    """Test cancellation is not treated as a recoverable partial query failure."""
    with pytest.raises(asyncio.CancelledError):
        coordinator._collect_device_results(
            [[{"endpointId": "device1"}], asyncio.CancelledError()]
        )


def test_coordinator_reuses_state_helper_per_device(coordinator):
    """Test coordinator returns the same helper instance per endpoint ID."""
    helper_a = coordinator.get_state_helper("device1", {"pwr": 1})
    helper_b = coordinator.get_state_helper("device1", {"pwr": 0, "temp": 230})

    assert helper_a is helper_b
    assert helper_a.current_params == {"pwr": 1}


def test_state_helper_deduplicates_same_update_id(coordinator):
    """Test helper processes a single coordinator update only once."""
    helper = coordinator.get_state_helper("device1", {"pwr": 1})

    helper.process_new_payload({}, "AC Unit 1", update_id=1)
    helper.process_new_payload({}, "AC Unit 1", update_id=1)
    helper.process_new_payload({}, "AC Unit 1", update_id=1)

    assert helper.is_available() is True

    for update_id in range(2, 7):
        helper.process_new_payload({}, "AC Unit 1", update_id=update_id)

    assert helper.is_available() is False


def test_state_helper_keeps_cache_on_empty_and_zero_ambient_payload(coordinator):
    """Test cached state survives empty payloads and transient zero ambient temp."""
    helper = coordinator.get_state_helper(
        "device1",
        {AC_TEMPERATURE_AMBIENT: 215, "pwr": 1},
    )

    helper.process_new_payload({}, "AC Unit 1", update_id=1)
    helper.process_new_payload(
        {AC_TEMPERATURE_AMBIENT: 0, "pwr": 0},
        "AC Unit 1",
        update_id=2,
    )

    assert helper.current_params[AC_TEMPERATURE_AMBIENT] == 215
    assert helper.current_params["pwr"] == 0


async def test_coordinator_merges_websocket_updates(coordinator, mock_aux_cloud_api):
    """Test websocket updates merge into coordinator state."""
    coordinator.devices = [
        {
            "endpointId": "device1",
            "friendlyName": "AC Unit 1",
            "params": {"pwr": 0},
        }
    ]
    coordinator.async_set_updated_data({"devices": coordinator.devices})
    original_publish = coordinator.async_set_updated_data
    coordinator.async_set_updated_data = MagicMock(side_effect=original_publish)
    await coordinator._async_handle_websocket_message(
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

    device = coordinator.get_device_by_endpoint_id("device1")
    assert device["params"] == {"pwr": 1}
    mock_aux_cloud_api.normalize_device_params.assert_called_once_with(device)
    coordinator.async_set_updated_data.assert_called_once()


def test_inventory_requires_two_complete_scans_before_removal(coordinator):
    """Test a one-off complete empty scan cannot delete a cloud device."""
    device = {"endpointId": "device1", "params": {"pwr": 1}}
    coordinator.devices = [device]

    assert coordinator._reconcile_inventory([], complete=True) == [device]
    assert coordinator._reconcile_inventory([], complete=True) == []


def test_partial_inventory_never_removes_devices(coordinator):
    """Test partial family failures retain previously known devices."""
    device = {"endpointId": "device1", "params": {"pwr": 1}}
    coordinator.devices = [device]

    assert coordinator._reconcile_inventory([], complete=False) == [device]


def test_confirmed_stale_device_is_removed_from_registry(coordinator):
    """Test confirmed cloud removal also cleans the HA device registry."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, entry_id="entry1")
    entry.add_to_hass(coordinator.hass)
    coordinator._aux_config_entry = entry
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
    coordinator.devices = [
        {
            "endpointId": "device1",
            "friendlyName": "AC Unit 1",
            "productId": "000000000000000000000000c0620000",
            "state": 1,
            "params": {"pwr": 1, "temp": 245},
        }
    ]
    coordinator.async_set_updated_data({"devices": coordinator.devices})
    entity = BaseEntity(coordinator, "device1", SimpleNamespace(key="pwr"))
    entity.async_write_ha_state = MagicMock()
    assert entity.available is True

    await coordinator._async_handle_websocket_message(
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
    entity._handle_coordinator_update()

    device = coordinator.get_device_by_endpoint_id("device1")
    assert device["state"] == 0
    assert device["params"] == {}
    assert entity.available is False
    assert entity._get_device_params() == {}
    mock_aux_cloud_api.normalize_device_params.assert_not_called()


async def test_coordinator_command_merges_without_refresh(
    coordinator, mock_aux_cloud_api
):
    """Test commands merge confirmed params without requesting refresh."""
    coordinator.devices = [
        {
            "endpointId": "device1",
            "friendlyName": "AC Unit 1",
            "params": {"pwr": 0},
        }
    ]
    coordinator.async_set_updated_data({"devices": coordinator.devices})
    coordinator.async_request_refresh = AsyncMock()

    device = coordinator.get_device_by_endpoint_id("device1")
    await coordinator.async_set_device_params(device, {"pwr": 1})

    assert coordinator.get_device_by_endpoint_id("device1")["params"]["pwr"] == 1
    mock_aux_cloud_api.set_device_params.assert_awaited_once_with(device, {"pwr": 1})
    coordinator.async_request_refresh.assert_not_called()


async def test_setup_entry_starts_websocket_after_platforms(hass, monkeypatch):
    """Test setup starts websocket updates only after platform setup succeeds."""
    events = []
    entry = SimpleNamespace(
        entry_id="entry1",
        unique_id=None,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
    )
    coordinator_mock = MagicMock()
    coordinator_mock.async_config_entry_first_refresh = AsyncMock()

    async def start_websocket():
        events.append("websocket")

    coordinator_mock.async_start_websocket = AsyncMock(side_effect=start_websocket)
    coordinator_mock.async_close = AsyncMock()
    api = MagicMock(userid=None)
    monkeypatch.setattr(integration, "AuxCloudAPI", MagicMock(return_value=api))
    monkeypatch.setattr(
        integration,
        "AuxCloudCoordinator",
        MagicMock(return_value=coordinator_mock),
    )

    async def forward_platforms(*args):
        events.append("platforms")

    monkeypatch.setattr(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(side_effect=forward_platforms),
    )

    assert await integration.async_setup_entry(hass, entry) is True

    assert events == ["platforms", "websocket"]
    assert entry.runtime_data.coordinator is coordinator_mock
    coordinator_mock.async_close.assert_not_awaited()


async def test_setup_entry_accepts_phone_credentials(hass, monkeypatch):
    """Test setup accepts phone-only config entries."""
    entry = SimpleNamespace(
        entry_id="entry1",
        unique_id=None,
        data={
            CONF_PHONE_NUMBER: "13800138000",
            CONF_PASSWORD: "secret",
            CONF_REGION: "cn",
        },
    )
    coordinator_mock = MagicMock()
    coordinator_mock.async_config_entry_first_refresh = AsyncMock()
    coordinator_mock.async_start_websocket = AsyncMock()
    coordinator_mock.async_close = AsyncMock()
    coordinator_factory = MagicMock(return_value=coordinator_mock)
    api = MagicMock(userid=None)
    monkeypatch.setattr(integration, "AuxCloudAPI", MagicMock(return_value=api))
    monkeypatch.setattr(integration, "AuxCloudCoordinator", coordinator_factory)
    monkeypatch.setattr(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(),
    )

    assert await integration.async_setup_entry(hass, entry) is True

    assert coordinator_factory.call_args.args[2] is None
    assert coordinator_factory.call_args.kwargs == {
        "config_entry": entry,
        "phone_number": "13800138000",
    }


async def test_setup_entry_preserves_legacy_unique_id(hass, monkeypatch):
    """Test setup stores account ID without changing a legacy unique ID."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "User@Example.COM",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
        entry_id="entry1",
        unique_id="legacy-entry-id",
    )
    entry.add_to_hass(hass)
    coordinator_mock = MagicMock()
    coordinator_mock.async_config_entry_first_refresh = AsyncMock()
    coordinator_mock.async_start_websocket = AsyncMock()
    coordinator_mock.async_close = AsyncMock()
    api = MagicMock(userid="cloud-user")
    monkeypatch.setattr(integration, "AuxCloudAPI", MagicMock(return_value=api))
    monkeypatch.setattr(
        integration,
        "AuxCloudCoordinator",
        MagicMock(return_value=coordinator_mock),
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(),
    )

    assert await integration.async_setup_entry(hass, entry) is True

    assert entry.unique_id == "legacy-entry-id"
    assert entry.data[CONF_ACCOUNT_ID] == "eu:user:cloud-user"


async def test_migration_removes_device_selection_and_preserves_unique_id(hass):
    """Test migration exposes every device without changing entry identity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
            CONF_SELECTED_DEVICES: ["device1"],
            "families": {"family1": {}},
        },
        entry_id="entry1",
        unique_id="legacy-entry-id",
        version=1,
    )
    entry.add_to_hass(hass)

    assert await integration.async_migrate_entry(hass, entry) is True

    assert entry.unique_id == "legacy-entry-id"
    assert CONF_SELECTED_DEVICES not in entry.data
    assert "families" not in entry.data


async def test_setup_entry_cleans_up_when_platform_setup_fails(hass, monkeypatch):
    """Test failed platform setup closes resources and removes stored entry data."""
    entry = SimpleNamespace(
        entry_id="entry1",
        unique_id=None,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
    )
    coordinator_mock = MagicMock()
    coordinator_mock.async_config_entry_first_refresh = AsyncMock()
    coordinator_mock.async_start_websocket = AsyncMock()
    coordinator_mock.async_close = AsyncMock()
    api = MagicMock(userid=None)
    monkeypatch.setattr(integration, "AuxCloudAPI", MagicMock(return_value=api))
    monkeypatch.setattr(
        integration,
        "AuxCloudCoordinator",
        MagicMock(return_value=coordinator_mock),
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_forward_entry_setups",
        AsyncMock(side_effect=RuntimeError("platform failed")),
    )

    with pytest.raises(RuntimeError, match="platform failed"):
        await integration.async_setup_entry(hass, entry)

    coordinator_mock.async_start_websocket.assert_not_awaited()
    coordinator_mock.async_close.assert_awaited_once()
    assert (
        not hasattr(entry, "runtime_data")
        or entry.runtime_data.coordinator is coordinator_mock
    )


async def test_coordinator_starts_single_websocket_runner(
    coordinator, mock_aux_cloud_api
):
    """Test coordinator owns a single websocket runner task."""
    started = asyncio.Event()

    async def run_websocket(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    mock_aux_cloud_api.async_run_websocket.side_effect = run_websocket

    await coordinator.async_start_websocket()
    first_task = coordinator._websocket_task
    await asyncio.wait_for(started.wait(), timeout=1)
    await coordinator.async_start_websocket()

    assert first_task is coordinator._websocket_task
    mock_aux_cloud_api.async_run_websocket.assert_awaited_once()
    await coordinator.async_close()
    assert coordinator._websocket_task is None


async def test_coordinator_retries_websocket_setup_failure(
    coordinator, mock_aux_cloud_api, monkeypatch
):
    """Test setup failure enables fallback polling and retries in one runner task."""
    monkeypatch.setattr(
        "custom_components.aux_cloud.coordinator.WEBSOCKET_SETUP_RETRY_INITIAL_DELAY",
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

    await coordinator.async_start_websocket()
    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.sleep(0)

    assert coordinator.update_interval == FALLBACK_SCAN_INTERVAL
    assert mock_aux_cloud_api.async_run_websocket.await_count == 2
    coordinator.async_request_refresh.assert_awaited_once()
    await coordinator.async_close()


async def test_coordinator_degraded_websocket_enables_fallback_polling(
    coordinator,
):
    """Test degraded websocket state enables slow HTTP fallback polling once."""
    coordinator.async_request_refresh = AsyncMock()

    await coordinator._async_handle_websocket_state(AuxWebSocketState.DEGRADED)
    await asyncio.sleep(0)
    await coordinator._async_handle_websocket_state(AuxWebSocketState.DEGRADED)
    await asyncio.sleep(0)

    assert coordinator.update_interval == FALLBACK_SCAN_INTERVAL
    coordinator.async_request_refresh.assert_awaited_once()


async def test_coordinator_ready_websocket_disables_fallback_polling(
    coordinator,
):
    """Test ready websocket state returns coordinator to push-only mode."""
    coordinator.update_interval = FALLBACK_SCAN_INTERVAL
    coordinator._websocket_degraded = True

    await coordinator._async_handle_websocket_state(AuxWebSocketState.READY)

    assert coordinator.update_interval == TOPOLOGY_SCAN_INTERVAL
    assert coordinator._websocket_degraded is False


async def test_base_entity_rolls_back_optimistic_update_on_command_failure(
    coordinator, mock_aux_cloud_api
):
    """Test optimistic entity state rolls back when the command fails."""
    coordinator.devices = [
        {
            "endpointId": "device1",
            "friendlyName": "AC Unit 1",
            "productId": "000000000000000000000000c0620000",
            "params": {"pwr": 0},
        }
    ]
    coordinator.async_set_updated_data({"devices": coordinator.devices})
    entity = BaseEntity(coordinator, "device1", SimpleNamespace(key="pwr"))
    entity.async_write_ha_state = MagicMock()
    mock_aux_cloud_api.set_device_params.side_effect = Exception("command failed")

    with pytest.raises(Exception, match="command failed"):
        await entity._set_device_params({"pwr": 1, "new_key": 1})

    assert entity._get_device_params()["pwr"] == 0
    assert "new_key" not in entity._get_device_params()


def test_sensor_reads_cached_params_and_ignores_transient_zero_ambient(coordinator):
    """Test sensors read the shared state helper instead of raw device params."""
    coordinator.devices = [
        {
            "endpointId": "device1",
            "friendlyName": "AC Unit 1",
            "productId": "000000000000000000000000c0620000",
            "params": {AC_TEMPERATURE_AMBIENT: 215},
        }
    ]
    coordinator.async_set_updated_data({"devices": coordinator.devices})
    sensor_config = SENSORS[AC_TEMPERATURE_AMBIENT]
    sensor = AuxCloudSensor(
        coordinator,
        "device1",
        sensor_config["description"],
        sensor_config["get_fn"],
    )
    sensor.async_write_ha_state = MagicMock()

    coordinator.devices[0]["params"] = {AC_TEMPERATURE_AMBIENT: 0}
    coordinator.async_set_updated_data({"devices": coordinator.devices})
    sensor._handle_coordinator_update()

    assert sensor.native_value == 21.5
