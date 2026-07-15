"""Behavior-focused AUX Cloud coordinator tests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.aux_cloud.state as state_module
from custom_components.aux_cloud import FALLBACK_SCAN_INTERVAL, AuxCloudCoordinator
from custom_components.aux_cloud.api.errors import AuxAuthError, AuxServerError
from custom_components.aux_cloud.api.models import DeviceUpdate, InventorySnapshot
from custom_components.aux_cloud.const import DOMAIN
from custom_components.aux_cloud.coordinator import TOPOLOGY_SCAN_INTERVAL
from custom_components.aux_cloud.devices import (
    HP_HOT_WATER_TEMPERATURE_TARGET,
)
from custom_components.aux_cloud.entity import BaseEntity

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def mock_aux_cloud_api():
    """Create a minimal API double."""
    api = MagicMock()
    api.is_logged_in.return_value = True
    api.login = AsyncMock()
    api.scan_devices = AsyncMock(
        return_value=InventorySnapshot((_device(),), complete=True)
    )
    api.run_realtime = AsyncMock()
    api.close = AsyncMock()
    api.update_realtime_devices = AsyncMock()
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
    mock_aux_cloud_api.scan_devices.return_value = InventorySnapshot(
        (_device(),), complete=True
    )
    assert list(await coordinator._async_update_data()) == ["device1"]

    mock_aux_cloud_api.scan_devices.return_value = InventorySnapshot(
        (_device(),), complete=False
    )
    assert (await coordinator._async_update_data())["device1"]["params"] == {"pwr": 1}

    mock_aux_cloud_api.scan_devices.side_effect = AuxAuthError(code=-1006)
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


async def test_realtime_client_health_controls_fallback_polling(
    coordinator, mock_aux_cloud_api
):
    """The coordinator maps client relay health onto its polling interval."""
    ready = asyncio.Event()

    async def run_realtime(*_args, **kwargs):
        kwargs["connection_listener"](True)
        ready.set()
        await asyncio.Event().wait()

    mock_aux_cloud_api.run_realtime.side_effect = run_realtime
    coordinator.async_request_refresh = AsyncMock()
    coordinator.start_realtime()
    task = coordinator._websocket_task
    coordinator.start_realtime()
    await asyncio.wait_for(ready.wait(), timeout=1)

    assert coordinator._websocket_task is task
    mock_aux_cloud_api.run_realtime.assert_awaited_once()
    assert coordinator.update_interval == TOPOLOGY_SCAN_INTERVAL
    assert coordinator.websocket_degraded is False

    coordinator._set_websocket_connected(False)
    await asyncio.sleep(0)
    assert coordinator.update_interval == FALLBACK_SCAN_INTERVAL
    await coordinator.async_close()
    assert coordinator._websocket_task is None
    mock_aux_cloud_api.close.assert_awaited_once()


async def test_command_transactions_rollback_without_overwriting_newer_push(
    coordinator, mock_aux_cloud_api
):
    """Stale ACKs do not flicker; failures roll back and pushes remain authoritative."""
    target = HP_HOT_WATER_TEMPERATURE_TARGET
    _seed(coordinator, [_device(params={target: 410})])
    entity = BaseEntity(coordinator, "device1", SimpleNamespace(key=target))
    entity.async_write_ha_state = MagicMock()

    mock_aux_cloud_api.set_device_params.side_effect = None
    mock_aux_cloud_api.set_device_params.return_value = {target: 410}
    await entity._set_device_params({target: 420})
    assert coordinator.get_device_by_endpoint_id("device1")["params"] == {target: 420}

    mock_aux_cloud_api.set_device_params.side_effect = AuxServerError("failed")
    with pytest.raises(HomeAssistantError):
        await entity._set_device_params({target: 430, "new": 1})
    assert coordinator.get_device_by_endpoint_id("device1")["params"] == {target: 420}

    coordinator._handle_websocket_updates((DeviceUpdate("device1", {target: 440}),))
    coordinator._handle_websocket_updates((DeviceUpdate("device1", {target: 420}),))
    assert coordinator.get_device_by_endpoint_id("device1")["params"] == {target: 420}

    started = asyncio.Event()

    async def wait_for_cancel(_device, _params):
        started.set()
        await asyncio.Event().wait()

    mock_aux_cloud_api.set_device_params.side_effect = wait_for_cancel
    command = asyncio.create_task(
        coordinator.async_set_device_params("device1", {target: 430, "new": 1})
    )
    await started.wait()
    coordinator._handle_websocket_updates((DeviceUpdate("device1", {target: 440}),))
    command.cancel()
    with pytest.raises(asyncio.CancelledError):
        await command
    assert coordinator.get_device_by_endpoint_id("device1")["params"] == {target: 440}


async def test_rapid_commands_ignore_only_recent_superseded_pushes(
    coordinator, mock_aux_cloud_api, monkeypatch
):
    """Delayed command pushes cannot replace the latest optimistic value."""
    now = 0.0
    monkeypatch.setattr(state_module, "monotonic", lambda: now)
    target = HP_HOT_WATER_TEMPERATURE_TARGET
    _seed(coordinator, [_device(params={target: 410})])

    await coordinator.async_set_device_params("device1", {target: 420})
    await coordinator.async_set_device_params("device1", {target: 430})

    coordinator._handle_websocket_updates((DeviceUpdate("device1", {target: 420}),))
    assert coordinator.get_device_by_endpoint_id("device1")["params"][target] == 430

    coordinator._handle_websocket_updates((DeviceUpdate("device1", {target: 440}),))
    assert coordinator.get_device_by_endpoint_id("device1")["params"][target] == 440
    coordinator._handle_websocket_updates((DeviceUpdate("device1", {target: 420}),))
    assert coordinator.get_device_by_endpoint_id("device1")["params"][target] == 440

    coordinator._handle_websocket_updates((DeviceUpdate("device1", {target: 430}),))
    coordinator._handle_websocket_updates((DeviceUpdate("device1", {target: 420}),))
    assert coordinator.get_device_by_endpoint_id("device1")["params"][target] == 420

    await coordinator.async_set_device_params("device1", {target: 430})
    await coordinator.async_set_device_params("device1", {target: 440})
    coordinator._handle_websocket_updates((DeviceUpdate("device1", {target: 430}),))
    assert coordinator.get_device_by_endpoint_id("device1")["params"][target] == 440

    now = 11.0
    coordinator._handle_websocket_updates((DeviceUpdate("device1", {target: 430}),))
    assert coordinator.get_device_by_endpoint_id("device1")["params"][target] == 430

    async def delayed_success(_device, _params):
        nonlocal now
        now += 11
        return {}

    mock_aux_cloud_api.set_device_params.side_effect = delayed_success
    await coordinator.async_set_device_params("device1", {target: 440})
    mock_aux_cloud_api.set_device_params.side_effect = None
    await coordinator.async_set_device_params("device1", {target: 450})
    coordinator._handle_websocket_updates((DeviceUpdate("device1", {target: 440}),))
    assert coordinator.get_device_by_endpoint_id("device1")["params"][target] == 450

    now = 31.0
    await coordinator.async_set_device_params("device1", {target: 460})
    now = 33.0
    coordinator._handle_websocket_updates((DeviceUpdate("device1", {target: 440}),))
    assert coordinator.get_device_by_endpoint_id("device1")["params"][target] == 440
