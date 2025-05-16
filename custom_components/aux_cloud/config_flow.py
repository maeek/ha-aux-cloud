"""Config flow to configure Aux Cloud."""

import base64
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .api.aux_cloud import AuxCloudAPI
from .const import DATA_AUX_CLOUD_CONFIG, DOMAIN, CONF_FAMILIES, CONF_SELECTED_DEVICES

_LOGGER = logging.getLogger(__name__)


# pylint: disable=abstract-method
class AuxCloudFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AUX Cloud."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the AUX Cloud flow."""
        self._aux_cloud = None
        self._email = None
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
        stored_email = (
            self.hass.data[DATA_AUX_CLOUD_CONFIG].get(CONF_EMAIL)
            if DATA_AUX_CLOUD_CONFIG in self.hass.data
            else ""
        )
        stored_password = (
            self.hass.data[DATA_AUX_CLOUD_CONFIG].get(CONF_PASSWORD)
            if DATA_AUX_CLOUD_CONFIG in self.hass.data
            else ""
        )
        stored_region = (
            self.hass.data[DATA_AUX_CLOUD_CONFIG].get(CONF_REGION)
            if DATA_AUX_CLOUD_CONFIG in self.hass.data
            else "eu"
        )

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]
            self._region = user_input[CONF_REGION]

            self._aux_cloud = AuxCloudAPI(region=self._region)

            try:
                await self._aux_cloud.login(self._email, self._password)

                # Fetch all families and devices after successful login
                return await self.async_step_fetch_devices()

            except Exception as ex:
                _LOGGER.error("Login failed: %s", ex)
                errors["base"] = "user_login_failed"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL, default=stored_email): str,
                vol.Required(CONF_PASSWORD, default=stored_password): str,
                vol.Required(CONF_REGION, default=stored_region): vol.In(
                    ["eu", "usa", "cn"]
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

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

                # Fetch devices for this family
                try:
                    devices = await self._aux_cloud.get_devices(family_id) or []
                    _LOGGER.debug(
                        "Family %s: Found %d personal devices", family_id, len(devices)
                    )
                except Exception as e:
                    _LOGGER.warning(
                        "Failed to fetch personal devices for family %s: %s",
                        family_id,
                        e,
                    )
                    devices = []

                try:
                    shared_devices = (
                        await self._aux_cloud.get_devices(family_id, shared=True) or []
                    )
                    _LOGGER.debug(
                        "Family %s: Found %d shared devices",
                        family_id,
                        len(shared_devices),
                    )
                except Exception as e:
                    _LOGGER.warning(
                        "Failed to fetch shared devices for family %s: %s",
                        family_id,
                        e,
                    )
                    shared_devices = []

                # Process devices
                all_family_devices = devices + shared_devices
                for device in all_family_devices:
                    device_id = device["endpointId"]
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
                _LOGGER.error("No devices found in any family")
                return self.async_abort(reason="no_devices_found")

            _LOGGER.debug(
                "Successfully processed %d devices across %d families",
                len(self._available_devices),
                len(self._families),
            )

            # Prepare device options for the multi_select
            device_options = {}
            for device in self._available_devices:
                device_id = device["id"]
                device_name = device["name"]
                family_name = device["family_name"]
                device_options[device_id] = (
                    f"{device['name']} ({device['family_name']})"
                )

            # Proceed to device selection step with a simpler schema using cv.multi_select
            return self.async_show_form(
                step_id="select_devices",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_SELECTED_DEVICES): cv.multi_select(
                            device_options
                        ),
                    }
                ),
                errors={},
                description_placeholders={
                    "devices_count": str(len(self._available_devices)),
                    "families_count": str(len(self._families)),
                },
            )

        except Exception as ex:
            _LOGGER.error("Error fetching devices: %s", ex)
            # Always return a flow result, never None
            return self.async_abort(reason="fetch_devices_failed")

    async def async_step_select_devices(self, user_input=None):
        """Allow the user to select which devices to add."""
        errors = {}

        if user_input is not None:
            try:
                selected_device_ids = user_input.get(CONF_SELECTED_DEVICES, [])

                # Convert to list if it's a single value
                if not isinstance(selected_device_ids, list):
                    selected_device_ids = [selected_device_ids]

                # Find the selected devices
                selected_devices = []
                for device_id in selected_device_ids:
                    for device in self._available_devices:
                        if device["id"] == device_id:
                            selected_devices.append(device)
                            break

                # Create config entry with the selected devices
                config = {
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_REGION: self._region,
                    CONF_SELECTED_DEVICES: selected_device_ids,
                    CONF_FAMILIES: self._families,
                }

                # Create an entry title based on the number of devices
                title = f"AUX Cloud ({len(selected_devices)} devices)"

                return self.async_create_entry(title=title, data=config)
            except Exception as ex:
                _LOGGER.error("Error creating entry: %s", ex)
                errors["base"] = "unknown"

        # Prepare device options for selection
        device_options = {}
        for device in self._available_devices:
            device_id = device["id"]
            device_name = device["name"]
            family_name = device["family_name"]
            device_options[device_id] = f"{device_name} ({family_name})"

        # If no devices were found, abort
        if not device_options:
            return self.async_abort(reason="no_devices_found")

        # Create a simple list of device options
        return self.async_show_form(
            step_id="select_devices",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SELECTED_DEVICES): cv.multi_select(
                        device_options
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "devices_count": str(len(self._available_devices)),
                "families_count": str(len(self._families)),
            },
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

            # Show a message in logs recommending UI configuration
            _LOGGER.info(
                "AUX Cloud configured via configuration.yaml. For better security, "
                "it is recommended to configure this integration through the UI where "
                "credentials are stored encrypted."
            )

            # Create a config entry directly from the imported data
            # For imports, we'll fetch and include all devices
            try:
                self._aux_cloud = AuxCloudAPI(region=self._region)
                await self._aux_cloud.login(self._email, self._password)

                # Fetch all families and devices
                families = await self._aux_cloud.get_families()

                all_devices = []
                for family in families:
                    family_id = family["familyid"]
                    devices = await self._aux_cloud.get_devices(family_id) or []
                    shared_devices = (
                        await self._aux_cloud.get_devices(family_id, shared=True) or []
                    )
                    all_devices.extend(devices + shared_devices)

                # Extract device IDs
                device_ids = [device["endpointId"] for device in all_devices]

                config = {
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_REGION: self._region,
                    CONF_SELECTED_DEVICES: device_ids,
                }

                return self.async_create_entry(
                    title=f"AUX Cloud ({len(device_ids)} devices)", data=config
                )

            except Exception as ex:
                _LOGGER.error("Import failed: %s", ex)
                return self.async_abort(reason="user_login_failed")

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
                    and (device_id := next(iter(identifiers[1:]))) in devices_to_remove
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
        password = self.config_entry.data.get(CONF_PASSWORD)
        region = self.config_entry.data.get(CONF_REGION, "eu")

        if not email or not password:
            return self.async_abort(reason="missing_credentials")

        try:
            self._aux_cloud = AuxCloudAPI(region=region)
            await self._aux_cloud.login(email, password)

            # Fetch all families and devices
            families = await self._aux_cloud.get_families()
            self._families = {}
            self._available_devices = []

            for family in families:
                family_id = family["familyid"]
                family_name = family["name"]

                # Store family info
                self._families[family_id] = {"name": family_name, "devices": []}

                devices = await self._aux_cloud.get_devices(family_id) or []
                shared_devices = (
                    await self._aux_cloud.get_devices(family_id, shared=True) or []
                )

                for device in devices + shared_devices:
                    device_id = device["endpointId"]
                    device_name = device["friendlyName"]
                    device_info = {
                        "id": device_id,
                        "name": device_name,
                        "family_id": family_id,
                        "family_name": family_name,
                    }
                    self._available_devices.append(device_info)
                    self._families[family_id]["devices"].append(device_info)

            # If no devices were found, display an error
            if not self._available_devices:
                return self.async_abort(reason="no_devices_found")

            # Create options for the form
            device_options = {}
            for device in self._available_devices:
                device_id = device["id"]
                device_name = device["name"]
                family_name = device["family_name"]
                device_options[device_id] = f"{device_name} ({family_name})"

            # Get currently selected devices
            current_devices = self.config_entry.data.get(CONF_SELECTED_DEVICES, [])

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
        except Exception as ex:
            _LOGGER.error("Error fetching devices: %s", ex)
            return self.async_abort(reason="fetch_devices_failed")
