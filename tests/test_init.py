"""Test component setup."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.helpers.translation import async_get_translations
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.aux_cloud as integration
from custom_components.aux_cloud import async_remove_config_entry_device, async_setup
from custom_components.aux_cloud.const import CONF_SELECTED_DEVICES, DOMAIN
from custom_components.aux_cloud.select import SELECTS


@pytest.mark.parametrize("language", ("en", "el", "pl"))
async def test_select_options_have_translations(hass, language):
    """Test every select option exposes a localized label to the frontend."""
    translations = await async_get_translations(
        hass, language, "entity", integrations={DOMAIN}
    )

    for description in SELECTS:
        translation_key = description.translation_key
        for option in description.value_by_option:
            assert (
                "component.aux_cloud.entity.select."
                f"{translation_key}.state.{option}" in translations
            )


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


async def test_manual_device_removal_only_allows_absent_devices(hass):
    """Test users cannot accidentally delete an active cloud device."""
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(data={"active": {"endpointId": "active"}})
    )

    assert not await async_remove_config_entry_device(
        hass,
        entry,
        SimpleNamespace(identifiers={("aux_cloud", "active")}),
    )
    assert await async_remove_config_entry_device(
        hass,
        entry,
        SimpleNamespace(identifiers={("aux_cloud", "removed")}),
    )


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
    assert entry.runtime_data is coordinator_mock
    coordinator_mock.async_close.assert_not_awaited()


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


async def test_migration_advances_version_two_minor_zero(hass):
    """Test a v2.0 entry is advanced once instead of migrating every startup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret"},
        version=2,
        minor_version=0,
    )
    entry.add_to_hass(hass)

    assert await integration.async_migrate_entry(hass, entry)
    assert entry.version == 2
    assert entry.minor_version == 1


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
    coordinator_mock.start_realtime = MagicMock()
    coordinator_mock.async_close = AsyncMock()
    api = MagicMock(user_id=None)
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

    coordinator_mock.start_realtime.assert_not_called()
    coordinator_mock.async_close.assert_awaited_once()
    assert not hasattr(entry, "runtime_data") or entry.runtime_data is coordinator_mock
