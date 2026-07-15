"""Test component setup."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.aux_cloud as integration
from custom_components.aux_cloud import async_setup
from custom_components.aux_cloud.const import CONF_SELECTED_DEVICES, DOMAIN


async def test_yaml_credentials_start_one_ui_import(hass, monkeypatch):
    """Test legacy YAML credentials are handed to the config flow without storage."""
    async_init = AsyncMock()
    monkeypatch.setattr(hass.config_entries.flow, "async_init", async_init)

    assert await async_setup(
        hass,
        {DOMAIN: {"email": "user@example.com", "password": "secret"}},
    )
    await hass.async_block_till_done()

    async_init.assert_awaited_once()
    assert DOMAIN not in hass.data


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

    def start_websocket():
        events.append("websocket")

    coordinator_mock.start_realtime = MagicMock(side_effect=start_websocket)
    coordinator_mock.async_close = AsyncMock()
    api = MagicMock(user_id=None)
    monkeypatch.setattr(integration, "DnaClient", MagicMock(return_value=api))
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
    assert entry.runtime_data is coordinator_mock
    coordinator_mock.async_close.assert_not_awaited()


async def test_migration_removes_device_selection_and_preserves_unique_id(hass):
    """Test legacy migrations preserve identity and settle on the current version."""
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

    v2_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret"},
        version=2,
        minor_version=0,
    )
    v2_entry.add_to_hass(hass)

    assert await integration.async_migrate_entry(hass, v2_entry)
    assert v2_entry.version == 2
    assert v2_entry.minor_version == 1
