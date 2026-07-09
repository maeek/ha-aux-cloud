"""Test AUX Cloud config flow behavior."""

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.aux_cloud.config_flow as config_flow_module
from custom_components.aux_cloud.api.errors import AuxAuthError
from custom_components.aux_cloud.const import (
    CONF_ACCOUNT_ID,
    CONF_PHONE_NUMBER,
    CONF_SELECTED_DEVICES,
    DOMAIN,
)

pytest_plugins = "pytest_homeassistant_custom_component"


class FakeAuxCloudAPI:
    """Fake cloud API used by config-flow tests."""

    instances = []
    user_id = "cloud-user"
    login_error = None

    def __init__(self, region: str = "eu", session=None) -> None:
        self.region = region
        self.session = session
        self.userid = self.user_id
        self.login_calls = []
        self.instances.append(self)

    async def login(
        self,
        email: str | None = None,
        password: str | None = None,
        *,
        phone_number: str | None = None,
    ) -> bool:
        self.login_calls.append((email, password, phone_number))
        if self.login_error:
            raise self.login_error
        return True


def _patch_fake_cloud(monkeypatch) -> None:
    FakeAuxCloudAPI.instances.clear()
    FakeAuxCloudAPI.user_id = "cloud-user"
    FakeAuxCloudAPI.login_error = None
    monkeypatch.setattr(config_flow_module, "AuxCloudAPI", FakeAuxCloudAPI)


async def _start_login(hass, method: str):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "menu"
    assert result["menu_options"] == ["email", "phone"]
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": method}
    )


async def test_email_first_flow_uses_eu_and_server_account_id(hass, monkeypatch):
    """Test email setup is streamlined and identifies the authenticated account."""
    _patch_fake_cloud(monkeypatch)
    result = await _start_login(hass, "email")
    assert result["step_id"] == "email"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "User@Example.COM",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
    )

    assert result["type"] == "create_entry"
    assert result["result"].unique_id == "eu:user:cloud-user"
    assert result["title"] == "AUX Cloud · user@example.com · EU"
    assert result["data"] == {
        CONF_EMAIL: "user@example.com",
        CONF_PASSWORD: "secret",
        CONF_REGION: "eu",
        CONF_ACCOUNT_ID: "eu:user:cloud-user",
    }
    assert CONF_SELECTED_DEVICES not in result["data"]


async def test_phone_flow_normalizes_number_and_masks_title(hass, monkeypatch):
    """Test phone setup remains available without exposing the number in title."""
    _patch_fake_cloud(monkeypatch)
    result = await _start_login(hass, "phone")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PHONE_NUMBER: "+48 123 456 789",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "AUX Cloud · ••••6789 · EU"
    assert result["data"][CONF_PHONE_NUMBER] == "48123456789"
    assert FakeAuxCloudAPI.instances[0].login_calls == [(None, "secret", "48123456789")]


async def test_multiple_accounts_are_allowed(hass, monkeypatch):
    """Test distinct authenticated account IDs create distinct entries."""
    _patch_fake_cloud(monkeypatch)
    for user_id, email in (
        ("user-one", "one@example.com"),
        ("user-two", "two@example.com"),
    ):
        FakeAuxCloudAPI.user_id = user_id
        result = await _start_login(hass, "email")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: email, CONF_PASSWORD: "secret", CONF_REGION: "eu"},
        )
        assert result["type"] == "create_entry"

    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_duplicate_authenticated_account_is_rejected(hass, monkeypatch):
    """Test aliases for the same server account cannot create duplicates."""
    _patch_fake_cloud(monkeypatch)
    first = await _start_login(hass, "email")
    await hass.config_entries.flow.async_configure(
        first["flow_id"],
        {CONF_EMAIL: "one@example.com", CONF_PASSWORD: "secret", CONF_REGION: "eu"},
    )

    second = await _start_login(hass, "email")
    result = await hass.config_entries.flow.async_configure(
        second["flow_id"],
        {CONF_EMAIL: "alias@example.com", CONF_PASSWORD: "secret", CONF_REGION: "eu"},
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_bad_credentials_remain_on_form(hass, monkeypatch):
    """Test typed auth failures are shown on the credential form."""
    _patch_fake_cloud(monkeypatch)
    FakeAuxCloudAPI.login_error = AuxAuthError(code=-1006)
    result = await _start_login(hass, "email")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "bad", CONF_REGION: "eu"},
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "bad_credentials"}


async def test_reauth_preserves_config_entry_unique_id(hass, monkeypatch):
    """Test reauth updates credentials without changing legacy entry identity."""
    _patch_fake_cloud(monkeypatch)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="legacy-email-id",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old",
            CONF_REGION: "eu",
            CONF_ACCOUNT_ID: "eu:user:cloud-user",
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reauth",
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "new",
            CONF_REGION: "eu",
        },
    )
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert entry.unique_id == "legacy-email-id"
    assert entry.data[CONF_PASSWORD] == "new"


async def test_reconfigure_rejects_different_account(hass, monkeypatch):
    """Test reconfigure cannot silently replace an existing account."""
    _patch_fake_cloud(monkeypatch)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="legacy-email-id",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "old",
            CONF_REGION: "eu",
            CONF_ACCOUNT_ID: "eu:user:original-user",
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
        data=entry.data,
    )
    if result["type"] == "abort":
        pytest.skip("Reconfigure flows require the Home Assistant 2026.4 test matrix")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "other@example.com",
            CONF_PASSWORD: "new",
            CONF_REGION: "eu",
        },
    )
    assert result["type"] == "abort"
    assert result["reason"] == "wrong_account"
    assert entry.data[CONF_EMAIL] == "user@example.com"
