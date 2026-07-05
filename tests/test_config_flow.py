"""Test AUX Cloud config flow behavior."""

# pylint: disable=invalid-name

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION

import custom_components.aux_cloud.config_flow as config_flow_module
from custom_components.aux_cloud.const import (
    CONF_CREDENTIAL_TYPE,
    CONF_PHONE_NUMBER,
    CONF_SELECTED_DEVICES,
    CREDENTIAL_TYPE_EMAIL,
    CREDENTIAL_TYPE_PHONE,
    DOMAIN,
)

pytest_plugins = "pytest_homeassistant_custom_component"


class FakeAuxCloudAPI:
    """Fake cloud API used by config-flow tests."""

    instances = []
    duplicate_shared_devices = False

    def __init__(self, region: str = "eu", session=None) -> None:
        """Initialize the fake API."""
        self.region = region
        self.session = session
        self.login_calls = []
        self.instances.append(self)

    async def login(
        self,
        email: str | None = None,
        password: str | None = None,
        *,
        phone_number: str | None = None,
    ) -> bool:
        """Record login calls."""
        self.login_calls.append(
            {
                "email": email,
                "password": password,
                "phone_number": phone_number,
            }
        )
        return True

    async def get_families(self) -> list[dict]:
        """Return one fake home."""
        return [{"familyid": "family1", "name": "Home"}]

    async def get_devices(self, family_id: str, shared: bool = False) -> list[dict]:
        """Return one personal device and no shared devices."""
        assert family_id == "family1"
        if shared and not self.duplicate_shared_devices:
            return []
        return [
            {
                "endpointId": "device1",
                "friendlyName": "AC Unit 1",
                "mac": "AA:BB:CC:DD:EE:FF",
                "productId": "000000000000000000000000c0620000",
                "roomId": "room1",
                "params": {"pwr": 1},
            }
        ]


def _patch_fake_cloud(monkeypatch) -> None:
    """Patch config flow to use the fake cloud API."""
    FakeAuxCloudAPI.instances.clear()
    FakeAuxCloudAPI.duplicate_shared_devices = False
    monkeypatch.setattr(config_flow_module, "AuxCloudAPI", FakeAuxCloudAPI)


async def _start_flow(hass):
    """Start the AUX Cloud config flow."""
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )


async def test_email_config_flow_keeps_legacy_email_storage(hass, monkeypatch):
    """Test email setup stores email and not phone fields."""
    _patch_fake_cloud(monkeypatch)

    result = await _start_flow(hass)
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CREDENTIAL_TYPE: CREDENTIAL_TYPE_EMAIL,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "AUX Cloud"
    assert result["result"].unique_id == "eu:email:user@example.com"
    assert result["data"][CONF_EMAIL] == "user@example.com"
    assert CONF_PHONE_NUMBER not in result["data"]
    assert result["data"][CONF_SELECTED_DEVICES] == ["device1"]
    assert FakeAuxCloudAPI.instances[0].login_calls == [
        {
            "email": "user@example.com",
            "password": "secret",
            "phone_number": None,
        }
    ]


async def test_phone_config_flow_adds_all_devices(hass, monkeypatch):
    """Test phone setup stores phone fields and all discovered devices."""
    _patch_fake_cloud(monkeypatch)

    result = await _start_flow(hass)
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CREDENTIAL_TYPE: CREDENTIAL_TYPE_PHONE,
            CONF_PHONE_NUMBER: "+8613800138000",
            CONF_PASSWORD: "secret",
            CONF_REGION: "cn",
        },
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "AUX Cloud"
    assert result["result"].unique_id == "cn:phone:8613800138000"
    assert CONF_EMAIL not in result["data"]
    assert result["data"][CONF_PHONE_NUMBER] == "8613800138000"
    assert result["data"][CONF_SELECTED_DEVICES] == ["device1"]
    assert FakeAuxCloudAPI.instances[0].login_calls == [
        {
            "email": None,
            "password": "secret",
            "phone_number": "8613800138000",
        }
    ]


async def test_phone_config_flow_accepts_arbitrary_phone_format(hass, monkeypatch):
    """Test phone setup accepts user-entered phone formatting without a code list."""
    _patch_fake_cloud(monkeypatch)

    result = await _start_flow(hass)
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CREDENTIAL_TYPE: CREDENTIAL_TYPE_PHONE,
            CONF_PHONE_NUMBER: "+999 123 456",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
    )

    assert result["type"] == "create_entry"
    assert result["result"].unique_id == "eu:phone:999123456"
    assert result["data"][CONF_PHONE_NUMBER] == "999123456"
    assert FakeAuxCloudAPI.instances[0].login_calls == [
        {
            "email": None,
            "password": "secret",
            "phone_number": "999123456",
        }
    ]


async def test_phone_config_flow_accepts_compact_phone_number(hass, monkeypatch):
    """Test phone setup accepts a compact user-entered phone number."""
    _patch_fake_cloud(monkeypatch)

    result = await _start_flow(hass)
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CREDENTIAL_TYPE: CREDENTIAL_TYPE_PHONE,
            CONF_PHONE_NUMBER: "+48123456789",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
    )

    assert result["type"] == "create_entry"
    assert result["result"].unique_id == "eu:phone:48123456789"
    assert result["data"][CONF_PHONE_NUMBER] == "48123456789"
    assert FakeAuxCloudAPI.instances[0].login_calls == [
        {
            "email": None,
            "password": "secret",
            "phone_number": "48123456789",
        }
    ]


async def test_config_flow_deduplicates_shared_device_selection(hass, monkeypatch):
    """Test duplicate personal/shared devices are stored once."""
    _patch_fake_cloud(monkeypatch)
    FakeAuxCloudAPI.duplicate_shared_devices = True

    result = await _start_flow(hass)
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CREDENTIAL_TYPE: CREDENTIAL_TYPE_EMAIL,
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_SELECTED_DEVICES] == ["device1"]
