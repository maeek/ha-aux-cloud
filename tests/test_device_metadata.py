"""AUX device metadata regression tests."""

import json

from custom_components.aux_cloud.device_metadata import (
    AUX_PROTOCOL_VERSION,
    get_cookie_profile_params,
    get_protocol_version,
    get_protocol_version_details,
)

from .api_helpers import mock_cookie, mock_heat_pump


def test_protocol_version_uses_only_valid_metadata() -> None:
    """Prefer observed versions and reject ambiguous vendor values."""
    external_version = mock_heat_pump(ver=4)
    external_version["cookie"] = mock_cookie(extend=json.dumps({"ver": 2}))
    assert get_protocol_version_details(external_version) == (4, "extern")

    cookie_version = mock_heat_pump()
    cookie_version.pop("extern")
    cookie_version["cookie"] = mock_cookie(extend=json.dumps({"ver": 3}))
    assert get_protocol_version_details(cookie_version) == (3, "cookie_extend")
    cookie_version[AUX_PROTOCOL_VERSION] = 5
    assert get_protocol_version_details(cookie_version) == (5, "session")

    malformed_cases = [
        ("not-json", "not-base64"),
        (json.dumps({"ver": True}), mock_cookie(extend={"ver": 3.5})),
        (json.dumps({"ver": "3"}), mock_cookie(extend={"ver": "3"})),
    ]
    for extern, cookie in malformed_cases:
        device = mock_heat_pump()
        device.update(extern=extern, cookie=cookie)
        assert get_protocol_version(device) is None


def test_cookie_profile_parameter_names_are_bounded() -> None:
    """Expose safe diagnostic names without leaking cookie contents."""
    device = mock_heat_pump(ver=2)
    device["cookie"] = mock_cookie(
        profile={"suids": [{"intfs": {"hp_pwr": [], "evidence": []}}]}
    )
    assert get_cookie_profile_params(device) == ("evidence", "hp_pwr")
