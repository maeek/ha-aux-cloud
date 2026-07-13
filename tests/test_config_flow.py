"""Test AUX Cloud config flow behavior."""

from types import SimpleNamespace

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.aux_cloud.config_flow as config_flow_module
from custom_components.aux_cloud.api.errors import AuxAuthError
from custom_components.aux_cloud.api.models import AuxCredentials
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
        self.login_calls = []
        self.instances.append(self)

    async def login(self, credentials: AuxCredentials) -> None:
        self.login_calls.append(credentials)
        if self.login_error:
            raise self.login_error


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
    assert FakeAuxCloudAPI.instances[0].login_calls == [
        AuxCredentials.phone("48123456789", "secret")
    ]


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
    assert result["type"] == "form", result
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


async def test_reconfigure_updates_credentials_for_same_account(hass, monkeypatch):
    """Test reconfigure shows a form and reloads matching account credentials."""
    _patch_fake_cloud(monkeypatch)
    entry = MockConfigEntry(
        domain=DOMAIN,
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
        context={"source": "reconfigure", "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] == "form"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "new",
            CONF_REGION: "eu",
        },
    )
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PASSWORD] == "new"


async def test_import_validates_required_fields_and_creates_entry(hass, monkeypatch):
    """Test YAML import rejects incomplete credentials and uses the normal login."""
    _patch_fake_cloud(monkeypatch)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "import"},
        data={CONF_EMAIL: "user@example.com"},
    )
    assert result["type"] == "abort"
    assert result["reason"] == "missing_credentials"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "import"},
        data={CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret"},
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_REGION] == "eu"


async def test_phone_and_unexpected_failures_stay_on_form(hass, monkeypatch):
    """Test empty phone input and unexpected validation failures are recoverable."""
    _patch_fake_cloud(monkeypatch)
    result = await _start_login(hass, "phone")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PHONE_NUMBER: "+ --", CONF_PASSWORD: "secret", CONF_REGION: "eu"},
    )
    assert result["errors"] == {"base": "phone_number_required"}

    FakeAuxCloudAPI.login_error = RuntimeError("unexpected")
    result = await _start_login(hass, "email")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret", CONF_REGION: "eu"},
    )
    assert result["errors"] == {"base": "unknown"}


async def test_missing_cloud_identity_aborts_safely(hass, monkeypatch):
    """Test a malformed successful login cannot create an unidentifiable entry."""
    _patch_fake_cloud(monkeypatch)
    FakeAuxCloudAPI.user_id = None
    result = await _start_login(hass, "email")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret", CONF_REGION: "eu"},
    )
    assert result["type"] == "abort"
    assert result["reason"] == "unknown"


def test_legacy_account_matching_and_credential_type():
    """Test pre-account-ID entries retain their legacy account checks."""
    flow = config_flow_module.AuxCloudFlowHandler()
    assert flow._same_target_account("account", {})

    flow._target_entry = SimpleNamespace(
        data={CONF_EMAIL: "User@Example.com", CONF_REGION: "eu"}
    )
    assert flow._same_target_account(
        "account", {CONF_EMAIL: "user@example.com", CONF_REGION: "eu"}
    )
    assert not flow._same_target_account(
        "account", {CONF_EMAIL: "user@example.com", CONF_REGION: "cn"}
    )

    flow._target_entry = SimpleNamespace(
        data={CONF_PHONE_NUMBER: "+48 123", CONF_REGION: "eu"}
    )
    assert flow._target_credential_type() == "phone"
    assert flow._same_target_account(
        "account", {CONF_PHONE_NUMBER: "48123", CONF_REGION: "eu"}
    )
