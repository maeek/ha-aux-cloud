"""Config flow for AUX Cloud."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    AuxApiError,
    AuxCloudAPI,
    config_flow_error_key,
)
from .const import (
    CONF_ACCOUNT_ID,
    CONF_FAMILIES,
    CONF_PHONE_NUMBER,
    CONF_SELECTED_DEVICES,
    DOMAIN,
)
from .util import (
    account_unique_id_from_credentials,
    account_unique_id_from_user_id,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult

_LOGGER = logging.getLogger(__name__)

REGION_OPTIONS = [
    "eu",
    "usa",
    "cn",
    "rus",
]


def _normalize_phone_number(value: str) -> str:
    """Normalize a user-entered phone number for AUX Cloud login."""
    return "".join(character for character in value if character.isdigit())


def _clean_entry_data(data: dict[str, Any]) -> dict[str, Any]:
    """Remove obsolete device-selection data without touching credentials."""
    return {
        key: value
        for key, value in data.items()
        if key not in {CONF_FAMILIES, CONF_SELECTED_DEVICES}
    }


class AuxCloudFlowHandler(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle an AUX Cloud config flow."""

    VERSION = 2
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize flow state."""
        self._target_entry: ConfigEntry | None = None
        self._mode = "create"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer email first while retaining phone login."""
        return self.async_show_menu(step_id="user", menu_options=["email", "phone"])

    async def async_step_email(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure an account using an email address."""
        return await self._async_account_step("email", user_input)

    async def async_step_phone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure an account using a phone number."""
        return await self._async_account_step("phone", user_input)

    async def async_step_import(self, import_info: dict[str, Any]) -> ConfigFlowResult:
        """Import legacy configuration.yaml credentials."""
        if not import_info.get(CONF_EMAIL) or not import_info.get(CONF_PASSWORD):
            return self.async_abort(reason="missing_credentials")
        return await self._async_validate_and_finish(
            "email",
            {
                CONF_EMAIL: import_info[CONF_EMAIL],
                CONF_PASSWORD: import_info[CONF_PASSWORD],
                CONF_REGION: import_info.get(CONF_REGION, "eu"),
            },
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start credential renewal for an existing entry."""
        self._target_entry = self._entry_for_flow("reauth")
        self._mode = "reauth"
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate replacement credentials and reload the entry."""
        return await self._async_account_step(
            self._target_credential_type(), user_input, step_id="reauth_confirm"
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update region or credentials while retaining the same account."""
        if self._target_entry is None:
            self._target_entry = self._entry_for_flow("reconfigure")
            self._mode = "reconfigure"
        return await self._async_account_step(
            self._target_credential_type(), user_input, step_id="reconfigure"
        )

    async def _async_account_step(
        self,
        credential_type: str,
        user_input: dict[str, Any] | None,
        *,
        step_id: str | None = None,
    ) -> ConfigFlowResult:
        """Show and process one credential-specific form."""
        step_id = step_id or credential_type
        if user_input is None:
            return self.async_show_form(
                step_id=step_id,
                data_schema=self._account_schema(credential_type),
            )

        normalized = dict(user_input)
        if credential_type == "email":
            normalized[CONF_EMAIL] = normalized[CONF_EMAIL].strip().lower()
        else:
            normalized[CONF_PHONE_NUMBER] = _normalize_phone_number(
                normalized[CONF_PHONE_NUMBER]
            )
            if not normalized[CONF_PHONE_NUMBER]:
                return self.async_show_form(
                    step_id=step_id,
                    data_schema=self._account_schema(credential_type, normalized),
                    errors={"base": "phone_number_required"},
                )

        try:
            return await self._async_validate_and_finish(credential_type, normalized)
        except AuxApiError as err:
            return self.async_show_form(
                step_id=step_id,
                data_schema=self._account_schema(credential_type, normalized),
                errors={"base": config_flow_error_key(err)},
            )
        except AbortFlow:
            raise
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected AUX Cloud credential validation failure")
            return self.async_show_form(
                step_id=step_id,
                data_schema=self._account_schema(credential_type, normalized),
                errors={"base": "unknown"},
            )

    async def _async_validate_and_finish(
        self, credential_type: str, user_input: dict[str, Any]
    ) -> ConfigFlowResult:
        """Authenticate, enforce account identity, and create/update the entry."""
        region = user_input.get(CONF_REGION, "eu")
        api = AuxCloudAPI(
            region=region,
            session=async_get_clientsession(self.hass),
        )
        if credential_type == "phone":
            await api.login(
                password=user_input[CONF_PASSWORD],
                phone_number=user_input[CONF_PHONE_NUMBER],
            )
        else:
            await api.login(user_input[CONF_EMAIL], user_input[CONF_PASSWORD])

        account_id = (
            account_unique_id_from_user_id(region, api.userid)
            if api.userid
            else account_unique_id_from_credentials(
                region,
                email=user_input.get(CONF_EMAIL),
                phone_number=user_input.get(CONF_PHONE_NUMBER),
            )
        )
        if account_id is None:
            return self.async_abort(reason="unknown")

        data = _clean_entry_data(user_input)
        data[CONF_ACCOUNT_ID] = account_id

        if self._target_entry is None:
            await self.async_set_unique_id(account_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=_entry_title(data),
                data=data,
            )

        if not self._same_target_account(account_id, data):
            return self.async_abort(reason="wrong_account")

        # Deliberately preserve existing config-entry unique IDs. Older versions
        # used credential-derived IDs and changing them provides no user benefit.
        return self.async_update_reload_and_abort(
            self._target_entry,
            title=_entry_title(data),
            data=data,
            reason=(
                "reauth_successful"
                if self._mode == "reauth"
                else "reconfigure_successful"
            ),
        )

    def _same_target_account(self, account_id: str, new_data: dict[str, Any]) -> bool:
        """Return whether validated credentials belong to the configured account."""
        if self._target_entry is None:
            return True
        stored_account_id = self._target_entry.data.get(CONF_ACCOUNT_ID)
        if stored_account_id:
            return stored_account_id == account_id

        old_data = self._target_entry.data
        if old_data.get(CONF_REGION, "eu") != new_data.get(CONF_REGION, "eu"):
            return False
        if old_data.get(CONF_EMAIL):
            return old_data[CONF_EMAIL].strip().lower() == new_data.get(CONF_EMAIL)
        return _normalize_phone_number(
            old_data.get(CONF_PHONE_NUMBER, "")
        ) == new_data.get(CONF_PHONE_NUMBER)

    def _target_credential_type(self) -> str:
        """Return the credential type used by the target entry."""
        if self._target_entry and self._target_entry.data.get(CONF_PHONE_NUMBER):
            return "phone"
        return "email"

    def _entry_for_flow(self, flow_type: str) -> ConfigEntry:
        """Return the target entry using current or legacy HA flow helpers."""
        helper = getattr(self, f"_get_{flow_type}_entry", None)
        if helper is not None:
            return helper()
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            raise ValueError("AUX Cloud config entry no longer exists")
        return entry

    def _account_schema(
        self,
        credential_type: str,
        submitted: dict[str, Any] | None = None,
    ) -> vol.Schema:
        """Return an email- or phone-specific schema with EU as default."""
        defaults = dict(self._target_entry.data) if self._target_entry else {}
        defaults.update(submitted or {})
        credential_key = CONF_PHONE_NUMBER if credential_type == "phone" else CONF_EMAIL
        credential_default = defaults.get(credential_key, "")
        return vol.Schema(
            {
                vol.Required(
                    credential_key, default=credential_default
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=(
                            selector.TextSelectorType.TEL
                            if credential_type == "phone"
                            else selector.TextSelectorType.EMAIL
                        ),
                        autocomplete=("tel" if credential_type == "phone" else "email"),
                    )
                ),
                vol.Required(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                        autocomplete="current-password",
                    )
                ),
                vol.Required(
                    CONF_REGION, default=defaults.get(CONF_REGION, "eu")
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=REGION_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="region",
                    )
                ),
            }
        )


def _entry_title(data: dict[str, Any]) -> str:
    """Return a concise account-specific title without exposing a full phone."""
    region = data.get(CONF_REGION, "eu").upper()
    if email := data.get(CONF_EMAIL):
        account = email
    else:
        phone = data.get(CONF_PHONE_NUMBER, "")
        account = f"••••{phone[-4:]}" if phone else "phone"
    return f"AUX Cloud · {account} · {region}"
