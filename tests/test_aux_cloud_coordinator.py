"""Test AUX Cloud coordinator functionality."""

from unittest.mock import MagicMock, AsyncMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.aux_cloud import AuxCloudCoordinator

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
    async def mock_get_devices(familyid, shared=False, selected_devices=None):
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
    return api


@pytest.fixture
def coordinator(hass, mock_aux_cloud_api):
    """Create an AuxCloudCoordinator instance."""
    return AuxCloudCoordinator(
        hass=hass,
        api=mock_aux_cloud_api,
        email="test@example.com",
        password="password123",
        selected_device_ids=["device1"],
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


async def test_coordinator_update_not_logged_in(coordinator, mock_aux_cloud_api):
    """Test coordinator update when not logged in."""
    # Simulate not logged in
    mock_aux_cloud_api.is_logged_in.return_value = False

    # Update should attempt login
    await coordinator._async_update_data()
    mock_aux_cloud_api.login.assert_called_once()


async def test_coordinator_update_login_failure(coordinator, mock_aux_cloud_api):
    """Test coordinator update when login fails."""
    # Simulate not logged in and login failure
    mock_aux_cloud_api.is_logged_in.return_value = False
    mock_aux_cloud_api.login.return_value = False

    # Update should fail with UpdateFailed
    with pytest.raises(UpdateFailed):
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
