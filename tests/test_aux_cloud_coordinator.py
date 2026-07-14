"""Behavior-focused AUX Cloud coordinator tests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.aux_cloud.coordinator as coordinator_module
from custom_components.aux_cloud import FALLBACK_SCAN_INTERVAL, AuxCloudCoordinator
from custom_components.aux_cloud.api.errors import AuxAuthError, AuxServerError
from custom_components.aux_cloud.api.models import DeviceUpdate
from custom_components.aux_cloud.const import DOMAIN
from custom_components.aux_cloud.coordinator import TOPOLOGY_SCAN_INTERVAL
from custom_components.aux_cloud.entity import BaseEntity

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def mock_aux_cloud_api():
    """Create a minimal API double."""
    api = MagicMock()
    api.is_logged_in.return_value = True
    api.login = AsyncMock()
    api.get_families = AsyncMock(
        return_value=[{"familyid": "family1", "name": "Family 1"}]
    )

    async def get_devices(_familyid, shared=False):
        return [] if shared else [_device()]

    api.get_devices = AsyncMock(side_effect=get_devices)
    api.async_run_websocket = AsyncMock()
    api.close_websocket = AsyncMock()
    api.async_update_websocket_subscriptions = AsyncMock()
    api.normalize_device_params = MagicMock()
    api.set_device_params = AsyncMock(return_value={"pwr": 1})
    api.user_id = None
    return api


@pytest.fixture
def coordinator(hass, mock_aux_cloud_api):
    """Create a coordinator with canonical account credentials."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "password123",
            CONF_REGION: "eu",
        },
    )
    entry.add_to_hass(hass)
    return AuxCloudCoordinator(hass, mock_aux_cloud_api, config_entry=entry)


def _device(**changes):
    return {
        "endpointId": "device1",
        "friendlyName": "AC Unit 1",
        "productId": "000000000000000000000000c0620000",
        "state": 1,
        "params": {"pwr": 1},
        **changes,
    }


def _seed(coordinator, devices) -> None:
    coordinator._state.reconcile(
        devices,
        complete=True,
        scan_revision=coordinator._state.revision,
    )
    coordinator._publish_devices()


async def test_refresh_isolates_partial_failures_and_auth_errors(
    coordinator, mock_aux_cloud_api
):
    """A usable account result wins; authentication failures still trigger reauth."""
    mock_aux_cloud_api.get_devices.side_effect = [
        [_device()],
        [_device(friendlyName="shared", params={"pwr": 0})],
    ]
    assert list(await coordinator._async_update_data()) == ["device1"]

    mock_aux_cloud_api.get_devices.side_effect = [
        [_device()],
        AuxServerError(http_status=503),
    ]
    assert (await coordinator._async_update_data())["device1"]["params"] == {"pwr": 1}

    mock_aux_cloud_api.get_devices.side_effect = AuxAuthError(code=-1006)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


def test_push_updates_merge_and_explicit_offline_clears_state(
    coordinator, mock_aux_cloud_api
):
    """Push data merges normally, while an explicit offline event drops stale params."""
    _seed(coordinator, [_device(params={"pwr": 0, "temp": 245})])
    coordinator._async_unsub_refresh = MagicMock()
    coordinator._handle_websocket_updates((DeviceUpdate("device1", {"pwr": 1}),))
    assert coordinator.get_device_by_endpoint_id("device1")["params"]["pwr"] == 1
    coordinator._async_unsub_refresh.assert_not_called()

    entity = BaseEntity(coordinator, "device1", SimpleNamespace(key="pwr"))
    entity.async_write_ha_state = MagicMock()
    coordinator._handle_websocket_updates(
        (DeviceUpdate("device1", {}, available=False),)
    )
    entity._handle_coordinator_update()

    assert coordinator.get_device_by_endpoint_id("device1")["params"] == {}
    assert entity.available is False
    mock_aux_cloud_api.normalize_device_params.assert_not_called()


async def test_realtime_supervisor_retries_once_and_restores_normal_polling(
    coordinator, mock_aux_cloud_api, monkeypatch
):
    """One runner retries a failed relay and switches polling with its health."""
    monkeypatch.setattr(coordinator_module, "WEBSOCKET_SETUP_RETRY_INITIAL_DELAY", 0)
    ready = asyncio.Event()
    attempts = 0

    async def run_websocket(*_args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise AuxServerError("relay unavailable")
        kwargs["on_ready"]()
        ready.set()
        await asyncio.Event().wait()

    mock_aux_cloud_api.async_run_websocket.side_effect = run_websocket
    coordinator.async_request_refresh = AsyncMock()
    coordinator.start_realtime()
    task = coordinator._websocket_task
    coordinator.start_realtime()
    await asyncio.wait_for(ready.wait(), timeout=1)

    assert coordinator._websocket_task is task
    assert attempts == 2
    assert coordinator.update_interval == TOPOLOGY_SCAN_INTERVAL
    assert coordinator.websocket_degraded is False

    coordinator._set_websocket_connected(False)
    await asyncio.sleep(0)
    assert coordinator.update_interval == FALLBACK_SCAN_INTERVAL
    await coordinator.async_close()
    assert coordinator._websocket_task is None


async def test_command_transactions_rollback_without_overwriting_newer_push(
    coordinator, mock_aux_cloud_api
):
    """Failed commands roll back, but a newer push remains authoritative."""
    _seed(coordinator, [_device(params={"pwr": 0})])
    entity = BaseEntity(coordinator, "device1", SimpleNamespace(key="pwr"))
    entity.async_write_ha_state = MagicMock()
    mock_aux_cloud_api.set_device_params.side_effect = AuxServerError("failed")
    with pytest.raises(HomeAssistantError):
        await entity._set_device_params({"pwr": 1, "new": 1})
    assert entity._get_device_params() == {"pwr": 0}

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
