"""Config flow to configure Aux Cloud."""
import json
import logging

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import selector

from .api.aux_cloud import AuxCloudAPI
from .api.const import AUX_MODELS
from .const import DATA_AUX_CLOUD_CONFIG, DOMAIN, CONF_SELECTED_DEVICES, CONF_FAMILIES

_LOGGER = logging.getLogger(__name__)


class AuxCloudFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AUX Cloud."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the AUX Cloud flow."""
        self._aux_cloud = None
        self._email = None
        self._password = None
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

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]

            self._aux_cloud = AuxCloudAPI()

            try:
                await self._aux_cloud.login(self._email, self._password)

                # Fetch all families and devices after successful login
                return await self.async_step_fetch_devices()

            except Exception as ex:
                _LOGGER.error(f"Login failed: {ex}")
                errors["base"] = "user_login_failed"

        data_schema = {
            vol.Required(CONF_EMAIL, default=stored_email): str,
            vol.Required(CONF_PASSWORD, default=stored_password): str,
        }

        if self.show_advanced_options:
            data_schema["region"] = selector({
                "select": {
                    "options": ["eu", "us"],
                    "translation_key": "region",
                }
            })

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=errors,
        )

    async def async_step_fetch_devices(self, user_input=None):
        """Fetch all families and devices."""
        if self._aux_cloud is None:
            return self.async_abort(reason="login_required")

        try:
            # Fetch all families
            families = await self._aux_cloud.list_families()

            # Process families and fetch devices for each family
            self._families = {}
            self._available_devices = []

            for family in families:
                family_id = family['familyid']
                family_name = family['name']

                # Decode base64 name if needed
                if '_' in family_name:
                    # Assume format is "<base64 encoded name>_<timestamp>"
                    try:
                        import base64
                        name_part = family_name.split('_')[0]
                        decoded_name = base64.b64decode(name_part).decode('utf-8')
                        family_name = decoded_name
                    except Exception:
                        # If decoding fails, use the original name
                        pass

                # Store family info
                self._families[family_id] = {
                    'name': family_name,
                    'devices': []
                }

                # Fetch devices for this family
                devices = await self._aux_cloud.list_devices(family_id) or []
                shared_devices = await self._aux_cloud.list_devices(family_id, shared=True) or []

                # Process devices
                all_family_devices = devices + shared_devices
                for device in all_family_devices:
                    device_id = device['endpointId']
                    device_name = device['friendlyName']
                    device_info = {
                        'id': device_id,
                        'name': device_name,
                        'family_id': family_id,
                        'family_name': family_name,
                        'mac': device['mac'],
                        'product_id': device['productId'],
                        'room_id': device.get('roomId', ''),
                    }

                    self._families[family_id]['devices'].append(device_info)
                    self._available_devices.append(device_info)

            # If no devices were found, display an error
            if not self._available_devices:
                return self.async_abort(reason="no_devices_found")

            # Proceed to device selection step
            return await self.async_step_select_devices()

        except Exception as ex:
            _LOGGER.error(f"Error fetching devices: {ex}")
            return self.async_abort(reason="fetch_devices_failed")

    async def list_devices(self, familyid: str, shared=False):
        """List devices for a family."""
        async with aiohttp.ClientSession() as session:
            device_endpoint = 'dev/query?action=select' if not shared else 'sharedev/querylist?querytype=shared'
            async with session.post(
                    f'{self.url}/appsync/group/{device_endpoint}',
                    data='{"pids":[]}' if not shared else '{"endpointId":""}',
                    headers=self._get_headers(familyid=familyid),
                    ssl=False
            ) as response:
                try:
                    data = await response.text()
                    json_data = json.loads(data)

                    if 'status' in json_data and json_data['status'] == 0:
                        devices = []  # Initialize with empty list

                        if 'endpoints' in json_data['data']:
                            devices = json_data['data']['endpoints']
                        elif 'shareFromOther' in json_data['data']:
                            devices = list(
                                map(lambda dev: dev['devinfo'], json_data['data']['shareFromOther']))
                        else:
                            # No devices found, return empty list
                            return devices

                        if devices:
                            for dev in devices:
                                try:
                                    # Check if the device is online
                                    dev_state = await self.query_device_state(dev['endpointId'], dev['devSession'])
                                    dev['state'] = dev_state['data'][0]['state']

                                    # Fetch known params of the device
                                    if dev['productId'] in AUX_MODELS and dev['state'] == 1:
                                        dev_params = await self.get_device_params(dev, params=list(
                                            AUX_MODELS[dev['productId']]['params'].keys()))
                                        dev['params'] = dev_params

                                        # Fetch additional params not returned with the
                                        # default query
                                        if len(AUX_MODELS[dev['productId']]['special_params']) != 0:
                                            dev_special_params = await self.get_device_params(dev, params=list(
                                                AUX_MODELS[dev['productId']]['special_params'].keys()))
                                            dev['params'] = {
                                                **dev['params'], **dev_special_params}

                                    # Fetch params from unknown device
                                    elif dev['state'] == 1:
                                        dev_params = await self.get_device_params(dev)
                                        dev['params'] = dev_params

                                except Exception as e:
                                    _LOGGER.error(f"Error processing device {dev.get('endpointId', 'unknown')}: {e}")
                                    dev['state'] = 0  # Mark as offline if we can't get state
                                    dev['params'] = {}

                                # Add to family devices if not already there
                                if hasattr(self, 'data') and familyid in self.data:
                                    if not any(d.get('endpointId') == dev.get('endpointId')
                                               for d in self.data[familyid].get('devices', [])):
                                        self.data[familyid]['devices'].append(dev)

                        return devices  # Always return devices, even if empty
                    else:
                        _LOGGER.warning(f"Failed to query devices: {data}")
                        return []  # Return empty list instead of raising exception

                except Exception as e:
                    _LOGGER.error(f"Exception in list_devices: {e}")
                    return []  # Always return a list even if an exception occurs

    async def async_step_import(self, import_info):
        """Import a config entry from configuration.yaml."""
        # Check if we already have a config entry
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        # Process the import_info
        if import_info and CONF_EMAIL in import_info and CONF_PASSWORD in import_info:
            self._email = import_info[CONF_EMAIL]
            self._password = import_info[CONF_PASSWORD]

            # Show a message in logs recommending UI configuration
            _LOGGER.info(
                "AUX Cloud configured via configuration.yaml. For better security, "
                "it is recommended to configure this integration through the UI where "
                "credentials are stored encrypted."
            )

            # Create a config entry directly from the imported data
            # For imports, we'll fetch and include all devices
            try:
                self._aux_cloud = AuxCloudAPI()
                await self._aux_cloud.login(self._email, self._password)

                # Fetch all families and devices
                families = await self._aux_cloud.list_families()

                all_devices = []
                for family in families:
                    family_id = family['familyid']
                    devices = await self._aux_cloud.list_devices(family_id)
                    shared_devices = await self._aux_cloud.list_devices(family_id, shared=True)
                    all_devices.extend(devices + shared_devices)

                # Extract device IDs
                device_ids = [device['endpointId'] for device in all_devices]

                config = {
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_SELECTED_DEVICES: device_ids,
                }

                return self.async_create_entry(
                    title=f"AUX Cloud ({len(device_ids)} devices)",
                    data=config
                )

            except Exception as ex:
                _LOGGER.error(f"Import failed: {ex}")

        # If import data is incomplete or login failed, show the form
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return AuxCloudOptionsFlowHandler(config_entry)


class AuxCloudOptionsFlowHandler(OptionsFlow):
    """Handle options flow for AUX Cloud."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self._aux_cloud = None
        self._available_devices = []
        self._families = {}

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is not None:
            # Update the config entry with new selected devices
            selected_device_ids = user_input.get(CONF_SELECTED_DEVICES, [])

            # Convert to list if it's a single value
            if not isinstance(selected_device_ids, list):
                selected_device_ids = [selected_device_ids]

            new_data = {
                **self.config_entry.data,
                CONF_SELECTED_DEVICES: selected_device_ids,
            }

            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )

            return self.async_create_entry(title="", data={})

        # Fetch all devices to allow re-selection
        email = self.config_entry.data.get(CONF_EMAIL)
        password = self.config_entry.data.get(CONF_PASSWORD)

        if not email or not password:
            return self.async_abort(reason="missing_credentials")


async def async_step_select_devices(self, user_input=None):
    """Allow the user to select which devices to add."""
    errors = {}

    if user_input is not None:
        selected_device_ids = user_input.get(CONF_SELECTED_DEVICES, [])

        # Convert to list if it's a single value
        if not isinstance(selected_device_ids, list):
            selected_device_ids = [selected_device_ids]

        # Find the selected devices
        selected_devices = []
        for device_id in selected_device_ids:
            for device in self._available_devices:
                if device['id'] == device_id:
                    selected_devices.append(device)
                    break

        # Create config entry with the selected devices
        config = {
            CONF_EMAIL: self._email,
            CONF_PASSWORD: self._password,
            CONF_SELECTED_DEVICES: selected_device_ids,
            CONF_FAMILIES: self._families,
        }

        # Create an entry title based on the number of devices
        title = f"AUX Cloud ({len(selected_devices)} devices)"

        return self.async_create_entry(title=title, data=config)

    # Prepare device options for selection
    device_options = {}
    for device in self._available_devices:
        device_id = device['id']
        device_name = device['name']
        family_name = device['family_name']
        device_options[device_id] = f"{device_name} ({family_name})"

    return self.async_show_form(
        step_id="select_devices",
        data_schema=vol.Schema({
            vol.Required(CONF_SELECTED_DEVICES): vol.All(
                cv.multi_select(device_options),
                vol.Length(min=1, msg="At least one device must be selected")
            ),
        }),
        errors=errors,
        description_placeholders={
            "devices_count": str(len(self._available_devices)),
            "families_count": str(len(self._families)),
        },
    )
