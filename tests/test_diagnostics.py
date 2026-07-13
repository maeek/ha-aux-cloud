"""AUX diagnostics tests."""

import base64
import json
from types import SimpleNamespace

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION

from custom_components.aux_cloud.diagnostics import async_get_config_entry_diagnostics

pytest_plugins = "pytest_homeassistant_custom_component"


async def test_diagnostics_redact_credentials_and_device_identity(hass):
    """Test downloadable diagnostics contain useful status but no secrets."""
    coordinator = SimpleNamespace(
        data={
            "device-secret": {
                "endpointId": "device-secret",
                "friendlyName": "Bedroom",
                "mac": "AA:BB:CC:DD:EE:FF",
                "cookie": "cookie-secret",
                "productId": "000000000000000000000000c0620000",
                "params": {"pwr": 1},
            }
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
        runtime_data=coordinator,
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
    assert diagnostics["devices"][0]["cookie_profile_params"] == []


async def test_diagnostics_sanitize_cookie_profile_and_version_source(hass):
    """Test cookie metadata is useful without exposing cookie secrets."""
    cookie = base64.b64encode(
        json.dumps(
            {
                "terminalid": 9876,
                "aeskey": "diagnostic-aes-secret",
                "extend": json.dumps({"ver": 2}),
                "profile": json.dumps(
                    {
                        "suids": [
                            {
                                "intfs": {
                                    "hp_pwr": [],
                                    "diagnostic_only": [],
                                }
                            }
                        ]
                    }
                ),
            }
        ).encode()
    ).decode()
    coordinator = SimpleNamespace(
        data={
            "device-secret": {
                "endpointId": "device-secret",
                "productId": "000000000000000000000000c3aa0000",
                "extern": json.dumps({"ver": 4}),
                "cookie": cookie,
                "params": {"hp_pwr": 1},
            }
        },
        last_update_success=True,
        update_interval=None,
        websocket_degraded=False,
    )
    entry = SimpleNamespace(data={}, runtime_data=coordinator)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    device = diagnostics["devices"][0]

    assert device["protocol_version"] == 4
    assert device["protocol_version_source"] == "extern"
    assert device["initial_param_queries"][0] == ["ver"]
    assert device["fallback_param_queries"] == []
    assert device["cookie_profile_params"] == ["diagnostic_only", "hp_pwr"]
    assert device["cookie_only_params"] == ["diagnostic_only"]
    assert "diagnostic-aes-secret" not in repr(diagnostics)
    assert "9876" not in repr(diagnostics)
