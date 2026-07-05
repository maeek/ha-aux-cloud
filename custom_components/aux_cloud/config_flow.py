"""Config flow to configure Aux Cloud."""

import base64
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .api import (
    AuxApiError,
    AuxAuthError,
    AuxCloudAPI,
    AuxSessionExpired,
    config_flow_error_key,
)
from .const import (
    CONF_CREDENTIAL_TYPE,
    CONF_FAMILIES,
    CONF_PHONE_NUMBER,
    CONF_SELECTED_DEVICES,
    CREDENTIAL_TYPE_EMAIL,
    CREDENTIAL_TYPE_PHONE,
    DATA_AUX_CLOUD_CONFIG,
    DOMAIN,
)
from .util import (
    account_unique_id_from_credentials,
    deduplicate_devices_by_endpoint_id,
    deduplicate_ordered_values,
)

_LOGGER = logging.getLogger(__name__)


async def _async_fetch_family_devices(
    aux_cloud: AuxCloudAPI, family_id: str
) -> tuple[list[dict], list[AuxApiError], int]:
    """Fetch personal and shared devices for one family, preserving partial success."""
    devices = []
    query_errors = []
    successful_queries = 0

    for shared in (False, True):
        query_label = "shared" if shared else "personal"
        try:
            query_devices = await aux_cloud.get_devices(family_id, shared=shared) or []
            _LOGGER.debug(
                "Family %s: Found %d %s devices",
                family_id,
                len(query_devices),
                query_label,
            )
            devices.extend(query_devices)
            successful_queries += 1
        except (AuxAuthError, AuxSessionExpired):
            raise
        except AuxApiError as err:
            query_errors.append(err)
            _LOGGER.warning(
                "Failed to fetch %s devices for family %s: %s",
                query_label,
                family_id,
                err,
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.warning(
                "Failed to fetch %s devices for family %s: %s",
                query_label,
                family_id,
                err,
            )

    return (
        deduplicate_devices_by_endpoint_id(devices),
        query_errors,
        successful_queries,
    )


def _preferred_device_discovery_error(errors: list[AuxApiError]) -> AuxApiError:
    """Return the most useful cloud error for failed device discovery."""
    return errors[0]


def _device_options(devices: list[dict]) -> dict[str, str]:
    """Return config-flow selection labels for discovered devices."""
    return {
        device["id"]: f"{device['name']} ({device['family_name']})"
        for device in devices
    }


def _normalize_phone_number(value: str) -> str:
    """Normalize a user-entered phone number for AUX Cloud login."""
    return "".join(character for character in value if character.isdigit())


# pylint: disable=abstract-method
class AuxCloudFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AUX Cloud."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the AUX Cloud flow."""
        self._aux_cloud = None
        self._email = None
        self._phone_number = None
        self._password = None
        self._region = "eu"
        self._families = {}
        self._available_devices = []

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""
        if self._async_current_entries():
            # Config entry already exists, only one allowed.
            return self.async_abort(reason="single_instance_allowed")

        errors = {}

        if user_input is not None:
            credential_type = user_input[CONF_CREDENTIAL_TYPE]
            if credential_type == CREDENTIAL_TYPE_PHONE:
                self._email = None
                self._region = user_input[CONF_REGION]
                self._phone_number = _normalize_phone_number(
                    user_input.get(CONF_PHONE_NUMBER, "")
                )
                self._password = user_input[CONF_PASSWORD]

                if not self._phone_number:
                    errors["base"] = "phone_number_required"
                else:
                    return await self._async_login_and_fetch_devices(user_input)
            else:
                self._email = user_input.get(CONF_EMAIL, "").strip()
                self._phone_number = None
                self._password = user_input[CONF_PASSWORD]
                self._region = user_input[CONF_REGION]

                if not self._email:
                    errors["base"] = "email_required"
                else:
                    return await self._async_login_and_fetch_devices(user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self._login_schema(user_input),
            errors=errors,
        )

    def _login_schema(self, user_input=None) -> vol.Schema:
        """Return the combined email/phone login form schema."""
        stored_config = self._stored_config()
        defaults = {**stored_config, **(user_input or {})}
        default_credential_type = defaults.get(
            CONF_CREDENTIAL_TYPE,
            CREDENTIAL_TYPE_PHONE
            if defaults.get(CONF_PHONE_NUMBER)
            else CREDENTIAL_TYPE_EMAIL,
        )
        default_region = defaults.get(
            CONF_REGION,
            "cn" if default_credential_type == CREDENTIAL_TYPE_PHONE else "eu",
        )

        return vol.Schema(
            {
                vol.Required(
                    CONF_CREDENTIAL_TYPE,
                    default=default_credential_type,
                ): vol.In(
                    {
                        CREDENTIAL_TYPE_EMAIL: "Email",
                        CREDENTIAL_TYPE_PHONE: "Phone number",
                    }
                ),
                vol.Optional(CONF_EMAIL, default=defaults.get(CONF_EMAIL, "")): str,
                vol.Optional(
                    CONF_PHONE_NUMBER,
                    default=defaults.get(CONF_PHONE_NUMBER, ""),
                ): str,
                vol.Required(
                    CONF_PASSWORD,
                    default=defaults.get(CONF_PASSWORD, ""),
                ): str,
                vol.Required(CONF_REGION, default=default_region): vol.In(
                    ["eu", "usa", "cn", "rus"]
                ),
            }
        )

    def _stored_config(self) -> dict:
        """Return imported YAML defaults if available."""
        if DATA_AUX_CLOUD_CONFIG in self.hass.data:
            return self.hass.data[DATA_AUX_CLOUD_CONFIG]
        return {}

    async def _async_login_and_fetch_devices(self, user_input: dict):
        """Login and fetch devices, returning config-flow errors on failure."""
        await self._async_set_account_unique_id()

        try:
            await self._async_login()
            return await self.async_step_fetch_devices()
        except AuxApiError as ex:
            _LOGGER.warning("AUX Cloud login failed: %s", ex)
            return self.async_show_form(
                step_id="user",
                data_schema=self._login_schema(user_input),
                errors={"base": config_flow_error_key(ex)},
            )
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected AUX Cloud login failure: %s", ex)
            return self.async_show_form(
                step_id="user",
                data_schema=self._login_schema(user_input),
                errors={"base": "unknown"},
            )

    async def _async_set_account_unique_id(self) -> None:
        """Set and validate the account-level unique ID for this flow."""
        account_unique_id = account_unique_id_from_credentials(
            self._region,
            email=self._email,
            phone_number=self._phone_number,
        )
        if account_unique_id is None:
            return

        await self.async_set_unique_id(account_unique_id)
        self._abort_if_unique_id_configured()

    async def _async_login(self) -> None:
        """Login using the configured email or phone credentials."""
        self._aux_cloud = AuxCloudAPI(
            region=self._region,
            session=async_get_clientsession(self.hass),
        )
        if self._phone_number:
            await self._aux_cloud.login(
                password=self._password,
                phone_number=self._phone_number,
            )
            return

        await self._aux_cloud.login(self._email, self._password)

    async def async_step_fetch_devices(self):
        """Fetch all families and devices."""
        if self._aux_cloud is None:
            return self.async_abort(reason="login_required")

        try:
            # Fetch all families
            families = await self._aux_cloud.get_families()
            _LOGGER.debug("Fetched %d families", len(families))

            # Log each family
            for family in families:
                _LOGGER.debug(
                    "Family: ID=%s, Name=%s", family["familyid"], family["name"]
                )

            # Process families and fetch devices for each family
            self._families = {}
            self._available_devices = []
            seen_device_ids = set()
            device_query_errors = []
            successful_device_queries = 0

            for family in families:
                family_id = family["familyid"]
                family_name = family["name"]

                # Decode base64 name if needed
                if "_" in family_name:
                    # Assume format is "<base64 encoded name>_<timestamp>"
                    try:
                        name_part = family_name.split("_")[0]
                        decoded_name = base64.b64decode(name_part).decode("utf-8")
                        family_name = decoded_name
                        _LOGGER.debug(
                            "Decoded family name from %s to %s",
                            family["name"],
                            family_name,
                        )
                    except Exception as e:
                        _LOGGER.warning("Failed to decode family name: %s", e)
                        # If decoding fails, use the original name

                # Store family info
                self._families[family_id] = {"name": family_name, "devices": []}

                family_devices, query_errors, successful_queries = (
                    await _async_fetch_family_devices(self._aux_cloud, family_id)
                )
                device_query_errors.extend(query_errors)
                successful_device_queries += successful_queries

                for device in family_devices:
                    device_id = device["endpointId"]
                    if device_id in seen_device_ids:
                        _LOGGER.debug("Skipping duplicate AUX Cloud device discovery")
                        continue
                    seen_device_ids.add(device_id)

                    device_name = device["friendlyName"]

                    # Log each device's details
                    _LOGGER.debug(
                        "Device: ID=%s, Name=%s, Family=%s, ProductID=%s",
                        device_id,
                        device_name,
                        family_name,
                        device.get("productId", "Unknown"),
                    )

                    if "params" in device:
                        _LOGGER.debug(
                            "Device %s params: %s", device_id, device.get("params", {})
                        )

                    device_info = {
                        "id": device_id,
                        "name": device_name,
                        "family_id": family_id,
                        "family_name": family_name,
                        "mac": device["mac"],
                        "product_id": device["productId"],
                        "room_id": device.get("roomId", ""),
                    }

                    self._families[family_id]["devices"].append(device_info)
                    self._available_devices.append(device_info)

            # If no devices were found, display an error
            if not self._available_devices:
                if successful_device_queries == 0 and device_query_errors:
                    error = _preferred_device_discovery_error(device_query_errors)
                    _LOGGER.warning("All AUX Cloud device queries failed: %s", error)
                    return self.async_abort(reason=config_flow_error_key(error))
                _LOGGER.error("No devices found in any family")
                return self.async_abort(reason="no_devices_found")

            _LOGGER.debug(
                "Successfully processed %d devices across %d families",
                len(self._available_devices),
                len(self._families),
            )

            return self._create_entry_with_devices()

        except AuxApiError as ex:
            _LOGGER.warning("AUX Cloud fetch devices failed: %s", ex)
            return self.async_abort(reason=config_flow_error_key(ex))
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.exception("Error fetching devices: %s", ex)
            # Always return a flow result, never None
            return self.async_abort(reason="fetch_devices_failed")

    def _create_entry_with_devices(self):
        """Create the config entry with all discovered devices selected."""
        selected_device_ids = deduplicate_ordered_values(
            device["id"] for device in self._available_devices
        )
        config = {
            CONF_PASSWORD: self._password,
            CONF_REGION: self._region,
            CONF_SELECTED_DEVICES: selected_device_ids,
            CONF_FAMILIES: self._families,
        }

        if self._phone_number:
            config[CONF_PHONE_NUMBER] = self._phone_number
        else:
            config[CONF_EMAIL] = self._email

        return self.async_create_entry(
            title="AUX Cloud",
            data=config,
        )

    async def async_step_import(self, import_info):
        """Import a config entry from configuration.yaml."""
        # Check if we already have a config entry
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        # Process the import_info
        if import_info and CONF_EMAIL in import_info and CONF_PASSWORD in import_info:
            self._email = import_info[CONF_EMAIL]
            self._password = import_info[CONF_PASSWORD]
            self._region = import_info.get(CONF_REGION, "eu")
            await self._async_set_account_unique_id()

            # Show a message in logs recommending UI configuration
            _LOGGER.info(
                "AUX Cloud configured via configuration.yaml. For better security, "
                "it is recommended to configure this integration through the UI where "
                "credentials are stored encrypted."
            )

            # Create a config entry directly from the imported data
            # For imports, we'll fetch and include all devices
            try:
                self._aux_cloud = AuxCloudAPI(
                    region=self._region, session=async_get_clientsession(self.hass)
                )
                await self._aux_cloud.login(self._email, self._password)

                # Fetch all families and devices
                families = await self._aux_cloud.get_families()

                all_devices = []
                device_query_errors = []
                successful_device_queries = 0
                for family in families:
                    family_id = family["familyid"]
                    family_devices, query_errors, successful_queries = (
                        await _async_fetch_family_devices(self._aux_cloud, family_id)
                    )
                    device_query_errors.extend(query_errors)
                    successful_device_queries += successful_queries
                    all_devices.extend(family_devices)

                all_devices = deduplicate_devices_by_endpoint_id(all_devices)

                if (
                    not all_devices
                    and successful_device_queries == 0
                    and device_query_errors
                ):
                    raise _preferred_device_discovery_error(device_query_errors)

                # Extract device IDs
                device_ids = deduplicate_ordered_values(
                    device["endpointId"] for device in all_devices
                )

                config = {
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_REGION: self._region,
                    CONF_SELECTED_DEVICES: device_ids,
                }

                return self.async_create_entry(
                    title="AUX Cloud", data=config
                )

            except AuxApiError as ex:
                _LOGGER.warning("AUX Cloud import failed: %s", ex)
                return self.async_abort(reason=config_flow_error_key(ex))
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Import failed: %s", ex)
                return self.async_abort(reason="unknown")

        # If import data is incomplete, show the form
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return AuxCloudOptionsFlowHandler()


class AuxCloudOptionsFlowHandler(OptionsFlow):
    """Handle options flow for AUX Cloud."""

    def __init__(self):
        """Initialize options flow."""
        self._aux_cloud = None
        self._available_devices = []
        self._families = {}

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is not None:
            try:
                # Update the config entry with new selected devices
                selected_device_ids = user_input.get(CONF_SELECTED_DEVICES, [])

                # Convert to list if it's a single value
                if not isinstance(selected_device_ids, list):
                    selected_device_ids = [selected_device_ids]
                selected_device_ids = deduplicate_ordered_values(selected_device_ids)

                # Get previously selected devices
                previous_device_ids = self.config_entry.data.get(
                    CONF_SELECTED_DEVICES, []
                )

                # Find devices to remove (previously selected but not in the new selection)
                devices_to_remove = set(previous_device_ids) - set(selected_device_ids)

                # Remove entities and devices from Home Assistant
                device_registry = async_get_device_registry(self.hass)
                entity_registry = async_get_entity_registry(self.hass)

                device_registry_filtered = [
                    device
                    for device in device_registry.devices.values()
                    if device.identifiers
                    for identifiers in device.identifiers
                    if len(identifiers) == 2
                    and identifiers[0] == DOMAIN
                    and identifiers[1] in devices_to_remove
                ]

                for device in device_registry_filtered:
                    for entity in list(entity_registry.entities.values()):
                        if entity.device_id == device.id:
                            entity_registry.async_remove(entity.entity_id)

                    device_registry.async_remove_device(device.id)

                # Update the config entry with the new selected devices
                new_data = {
                    **self.config_entry.data,
                    CONF_SELECTED_DEVICES: selected_device_ids,
                }

                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )

                self.hass.config_entries.async_schedule_reload(
                    self.config_entry.entry_id
                )

                return self.async_create_entry(title="", data={})
            except Exception as ex:
                _LOGGER.error("Error updating config entry: %s", ex)
        # Fetch all devices to allow re-selection
        email = self.config_entry.data.get(CONF_EMAIL)
        phone_number = self.config_entry.data.get(CONF_PHONE_NUMBER)
        password = self.config_entry.data.get(CONF_PASSWORD)
        region = self.config_entry.data.get(CONF_REGION, "eu")

        if not password or not (email or phone_number):
            return self.async_abort(reason="missing_credentials")

        try:
            no_devices_reason = await self._async_fetch_available_devices(
                email,
                password,
                region,
                phone_number=phone_number,
            )
            if no_devices_reason:
                return self.async_abort(reason=no_devices_reason)

            # Create options for the form
            device_options = _device_options(self._available_devices)

            # Get currently selected devices
            current_devices = deduplicate_ordered_values(
                self.config_entry.data.get(CONF_SELECTED_DEVICES, [])
            )

            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_SELECTED_DEVICES, default=current_devices
                        ): cv.multi_select(device_options),
                    }
                ),
                description_placeholders={
                    "devices_count": str(len(self._available_devices)),
                    "families_count": str(len(self._families)),
                },
            )
        except AuxApiError as ex:
            _LOGGER.warning("AUX Cloud options fetch devices failed: %s", ex)
            return self.async_abort(reason=config_flow_error_key(ex))
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.exception("Error fetching devices: %s", ex)
            return self.async_abort(reason="fetch_devices_failed")

    async def _async_fetch_available_devices(
        self,
        email: str | None,
        password: str,
        region: str,
        *,
        phone_number: str | None = None,
    ) -> str | None:
        """Fetch devices for the options flow and return an abort reason if empty."""
        self._aux_cloud = AuxCloudAPI(
            region=region, session=async_get_clientsession(self.hass)
        )
        if phone_number:
            await self._aux_cloud.login(
                password=password,
                phone_number=phone_number,
            )
        else:
            await self._aux_cloud.login(email, password)

        families = await self._aux_cloud.get_families()
        self._families = {}
        self._available_devices = []
        seen_device_ids = set()
        device_query_errors = []
        successful_device_queries = 0

        for family in families:
            family_id = family["familyid"]
            family_name = family["name"]
            self._families[family_id] = {"name": family_name, "devices": []}

            family_devices, query_errors, successful_queries = (
                await _async_fetch_family_devices(self._aux_cloud, family_id)
            )
            device_query_errors.extend(query_errors)
            successful_device_queries += successful_queries

            for device in family_devices:
                device_id = device["endpointId"]
                if device_id in seen_device_ids:
                    _LOGGER.debug("Skipping duplicate AUX Cloud options device")
                    continue
                seen_device_ids.add(device_id)

                device_info = {
                    "id": device_id,
                    "name": device["friendlyName"],
                    "family_id": family_id,
                    "family_name": family_name,
                }
                self._available_devices.append(device_info)
                self._families[family_id]["devices"].append(device_info)

        if self._available_devices:
            return None
        if successful_device_queries == 0 and device_query_errors:
            error = _preferred_device_discovery_error(device_query_errors)
            _LOGGER.warning("All AUX Cloud option device queries failed: %s", error)
            return config_flow_error_key(error)
        return "no_devices_found"
