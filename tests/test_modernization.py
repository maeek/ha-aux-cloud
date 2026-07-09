"""Regression tests for the modern Home Assistant integration contract."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aux_cloud import async_remove_config_entry_device
from custom_components.aux_cloud.api.errors import parse_retry_after
from custom_components.aux_cloud.api.session import REQUEST_TIMEOUT, AuxCloudSession
from custom_components.aux_cloud.diagnostics import async_get_config_entry_diagnostics
from custom_components.aux_cloud.util import (
    collision_safe_entity_unique_id,
    device_identifier,
    legacy_entity_unique_id,
)

pytest_plugins = "pytest_homeassistant_custom_component"


def test_legacy_registry_identifiers_are_frozen():
    """Test released entity and device identifiers remain byte-for-byte stable."""
    assert legacy_entity_unique_id("00001234", "ac") == "aux_cloud_1234_ac"
    assert legacy_entity_unique_id("device-1", "pwr") == "aux_cloud_device-1_pwr"
    assert device_identifier("00001234") == ("aux_cloud", "00001234")


def test_second_account_uses_v2_id_for_shared_entity(hass):
    """Test overlapping multi-account devices do not collide in the registry."""
    first_entry = MockConfigEntry(domain="aux_cloud", unique_id="eu:user:first")
    second_entry = MockConfigEntry(domain="aux_cloud", unique_id="eu:user:second")
    first_entry.add_to_hass(hass)
    second_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=first_entry.entry_id,
        identifiers={("aux_cloud", "device1")},
    )
    er.async_get(hass).async_get_or_create(
        "switch",
        "aux_cloud",
        "aux_cloud_device1_pwr",
        config_entry=first_entry,
        device_id=device.id,
    )

    unique_id = collision_safe_entity_unique_id(
        hass,
        "switch",
        "device1",
        "pwr",
        set(),
        config_entry_id=second_entry.entry_id,
        identity_salt=second_entry.unique_id,
    )

    assert unique_id.startswith("aux_cloud_device1_pwr_v2_")


def test_retry_after_is_clamped():
    """Test cloud backoff cannot cause a busy loop or multi-hour stall."""
    assert parse_retry_after("0") == 1
    assert parse_retry_after("120") == 120
    assert parse_retry_after("99999") == 3600
    assert parse_retry_after("not-a-date") is None


async def test_http_transport_uses_timeout_and_default_tls_verification():
    """Test HTTP requests set explicit timeouts and never disable TLS."""
    response = MagicMock(status=200, headers={})
    response.text = AsyncMock(return_value='{"status": 0}')
    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=response)
    context_manager.__aexit__ = AsyncMock(return_value=False)
    client = MagicMock()
    client.request.return_value = context_manager

    session = AuxCloudSession(session=client)
    await session._request_once(
        client,
        method="POST",
        url="https://example.com/test",
        endpoint="test",
        headers={},
        data=None,
        data_raw=None,
        params=None,
    )

    request_kwargs = client.request.call_args.kwargs
    assert request_kwargs["timeout"] is REQUEST_TIMEOUT
    assert "ssl" not in request_kwargs


async def test_session_recovery_is_single_flight():
    """Test concurrent expired requests share one replacement login."""
    session = AuxCloudSession()
    session.email = "user@example.com"
    session.password = "secret"
    session.loginsession = "expired"
    session.userid = "user"

    async def login_once(*args, **kwargs):
        await asyncio.sleep(0)
        session.loginsession = "fresh"
        session.userid = "user"
        return True

    session._login_unlocked = AsyncMock(side_effect=login_once)

    assert await asyncio.gather(
        session.recover_session(expired_session="expired"),
        session.recover_session(expired_session="expired"),
    ) == [True, True]
    session._login_unlocked.assert_awaited_once()


async def test_diagnostics_redact_credentials_and_device_identity(hass):
    """Test downloadable diagnostics contain useful status but no secrets."""
    coordinator = SimpleNamespace(
        data={
            "devices": [
                {
                    "endpointId": "device-secret",
                    "friendlyName": "Bedroom",
                    "mac": "AA:BB:CC:DD:EE:FF",
                    "cookie": "cookie-secret",
                    "productId": "000000000000000000000000c0620000",
                    "params": {"pwr": 1},
                }
            ]
        },
        last_update_success=True,
        update_interval=None,
        websocket_degraded=False,
    )
    entry = SimpleNamespace(
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["runtime"]["device_count"] == 1
    assert diagnostics["entry"][CONF_EMAIL] == "**REDACTED**"
    assert diagnostics["entry"][CONF_PASSWORD] == "**REDACTED**"
    assert "endpointId" not in diagnostics["devices"][0]
    assert "cookie" not in diagnostics["devices"][0]
    assert "params" not in diagnostics["devices"][0]
    assert diagnostics["devices"][0]["reported_param_names"] == ["pwr"]
    assert diagnostics["devices"][0]["profile"] == "AUX Air Conditioner"


async def test_manual_device_removal_only_allows_absent_devices(hass):
    """Test users cannot accidentally delete an active cloud device."""
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(
            coordinator=SimpleNamespace(devices=[{"endpointId": "active"}])
        )
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
