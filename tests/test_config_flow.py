"""Behavior-level tests for the AUX Cloud config flow."""

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.aux_cloud.config_flow as config_flow_module
from custom_components.aux_cloud.api.models import AuxCredentials
from custom_components.aux_cloud.const import (
    CONF_ACCOUNT_ID,
    CONF_PHONE_NUMBER,
    DOMAIN,
)

pytest_plugins = "pytest_homeassistant_custom_component"


class FakeAuxCloudAPI:
    """Small authenticated API boundary used by the flow tests."""

    instances = []
    user_id = "cloud-user"
    login_error = None

    def __init__(self, region: str = "eu", session=None) -> None:
        self.region = region
        self.session = session
        self.login_calls = []
        self.instances.append(self)

    async def login(self, credentials: AuxCredentials) -> None:
        self.login_calls.append(credentials)
        if self.login_error:
            raise self.login_error


def _patch_cloud(monkeypatch) -> None:
    FakeAuxCloudAPI.instances.clear()
    FakeAuxCloudAPI.user_id = "cloud-user"
    FakeAuxCloudAPI.login_error = None
    monkeypatch.setattr(config_flow_module, "AuxCloudAPI", FakeAuxCloudAPI)


async def _login_form(hass, method: str):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["menu_options"] == ["email", "phone"]
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": method}
    )


async def _submit_email(hass, email: str = "user@example.com"):
    result = await _login_form(hass, "email")
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: email, CONF_PASSWORD: "secret", CONF_REGION: "eu"},
    )


async def test_user_flows_normalize_credentials_and_use_cloud_identity(
    hass, monkeypatch
):
    """Email and phone setup normalize input without exposing phone numbers."""
    _patch_cloud(monkeypatch)
    email = await _submit_email(hass, "User@Example.COM")
    assert email["type"] == "create_entry"
    assert email["result"].unique_id == "eu:user:cloud-user"
    assert email["data"][CONF_EMAIL] == "user@example.com"

    FakeAuxCloudAPI.user_id = "phone-user"
    phone_form = await _login_form(hass, "phone")
    phone = await hass.config_entries.flow.async_configure(
        phone_form["flow_id"],
        {
            CONF_PHONE_NUMBER: "+48 123 456 789",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
    )
    assert phone["type"] == "create_entry"
    assert phone["title"] == "AUX Cloud · ••••6789 · EU"
    assert phone["data"][CONF_PHONE_NUMBER] == "48123456789"
    assert FakeAuxCloudAPI.instances[-1].login_calls == [
        AuxCredentials.phone("48123456789", "secret")
    ]


async def test_authenticated_account_identity_prevents_alias_duplicates(
    hass, monkeypatch
):
    """Cloud account IDs allow distinct accounts and reject aliases."""
    _patch_cloud(monkeypatch)
    assert (await _submit_email(hass, "one@example.com"))["type"] == "create_entry"

    duplicate = await _submit_email(hass, "alias@example.com")
    assert duplicate["type"] == "abort"
    assert duplicate["reason"] == "already_configured"

    FakeAuxCloudAPI.user_id = "second-user"
    distinct = await _submit_email(hass, "two@example.com")
    assert distinct["type"] == "create_entry"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_reauth_and_reconfigure_preserve_entry_identity(hass, monkeypatch):
    """Credential maintenance cannot silently replace the configured account."""
    _patch_cloud(monkeypatch)
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

    reauth = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        reauth["flow_id"],
        {
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "new",
            CONF_REGION: "eu",
        },
    )
    assert result["reason"] == "reauth_successful"
    assert entry.unique_id == "legacy-email-id"
    assert entry.data[CONF_PASSWORD] == "new"

    FakeAuxCloudAPI.user_id = "different-user"
    reconfigure = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        reconfigure["flow_id"],
        {
            CONF_EMAIL: "other@example.com",
            CONF_PASSWORD: "replacement",
            CONF_REGION: "eu",
        },
    )
    assert result["reason"] == "wrong_account"
    assert entry.data[CONF_EMAIL] == "user@example.com"
