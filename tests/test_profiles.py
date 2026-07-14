"""Device-profile and normalization regression tests."""

import json

from custom_components.aux_cloud.devices.normalizers import (
    decode_v3_hp_tank_temp_from_key_states,
    normalize_device_params,
)
from custom_components.aux_cloud.devices.profiles import (
    AC_MODE_SPECIAL,
    AC_POWER,
    AC_POWER_LIMIT,
    AC_TEMPERATURE_CONVERSION,
    AC_TEMPERATURE_DECIMAL,
    AC_TEMPERATURE_TARGET,
    AC_TEMPERATURE_UNIT,
    AUX_PROTOCOL_VERSION,
    HP_HOT_WATER_TANK_TEMPERATURE,
    V3_HEAT_PUMP_QUERIES,
    encode_ac_temperature_command,
    get_cookie_profile_params,
    get_product_profile,
    get_protocol_version,
    get_protocol_version_details,
)

from .api_helpers import mock_cookie, mock_device, mock_heat_pump


def test_profiles_own_safe_query_plans_and_protocol_resolution():
    """Profiles select audited AC/HP queries without response-derived discovery."""
    ac = mock_device()
    ac_profile = get_product_profile(ac["productId"])
    assert ac_profile.initial_param_queries(ac) == [[], [AC_MODE_SPECIAL]]
    assert AC_POWER in ac_profile.params

    legacy = mock_heat_pump(ver=2)
    legacy_profile = get_product_profile(legacy["productId"])
    assert legacy_profile.initial_param_queries(legacy) == [
        [],
        [HP_HOT_WATER_TANK_TEMPERATURE],
    ]
    v3 = mock_heat_pump(ver=4)
    v3["cookie"] = mock_cookie(extend=json.dumps({"ver": 2}))
    assert get_protocol_version_details(v3) == (4, "extern")
    assert legacy_profile.initial_param_queries(v3) == [
        list(query) for query in V3_HEAT_PUMP_QUERIES
    ]

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
        assert legacy_profile.initial_param_queries(device) == [
            [],
            [HP_HOT_WATER_TANK_TEMPERATURE],
        ]

    diagnostic = mock_heat_pump(ver=2)
    diagnostic["cookie"] = mock_cookie(
        profile={"suids": [{"intfs": {"hp_pwr": [], "evidence": []}}]}
    )
    assert get_cookie_profile_params(diagnostic) == ("evidence", "hp_pwr")
    assert get_product_profile("unknown").initial_param_queries(mock_device()) == []


def test_profiles_enforce_product_specific_command_quirks():
    """Audited products expose only their verified modes and writable controls."""
    constraints = [
        ("28620000", False, True, True, True),
        ("45620000", False, True, True, False),
        ("56ac0000", True, False, False, True),
        ("a44e0000", True, False, False, True),
        ("c5510000", False, True, True, True),
        ("c9100100", False, True, True, False),
    ]
    for suffix, auto, extended_fan, horizontal, power_limit in constraints:
        profile = get_product_profile(f"{'0' * 24}{suffix}")
        assert (4 in profile.hvac_modes) is auto
        assert (6 in profile.fan_speeds and 7 in profile.fan_speeds) is extended_fan
        assert profile.horizontal_swing is horizontal
        assert (AC_POWER_LIMIT in profile.writable_params) is power_limit

    heat_pump = mock_heat_pump(ver=4)
    params, vals = get_product_profile(heat_pump["productId"]).prepare_command(
        heat_pump, ["hp_pwr"], [[{"idx": 1, "val": 1}]]
    )
    assert params == ["hp_pwr", "ver"]
    assert vals[-1] == [{"idx": 1, "val": 4}]


def test_ac_temperature_wire_formats_round_trip():
    """Standard, Fahrenheit and half-degree products retain exact targets."""
    assert encode_ac_temperature_command(mock_device(), 16.5) == {
        AC_TEMPERATURE_TARGET: 165
    }

    fahrenheit = mock_device()
    fahrenheit["params"] = {AC_TEMPERATURE_UNIT: 2}
    encoded = encode_ac_temperature_command(fahrenheit, 17.2)
    assert encoded == {
        AC_TEMPERATURE_TARGET: 170,
        AC_TEMPERATURE_UNIT: 2,
        AC_TEMPERATURE_DECIMAL: 0,
        AC_TEMPERATURE_CONVERSION: 2,
    }
    fahrenheit["params"] = encoded
    normalize_device_params(fahrenheit)
    assert fahrenheit["params"][AC_TEMPERATURE_TARGET] == 172
    assert (
        encode_ac_temperature_command(fahrenheit, (66 - 32) / 1.8)[
            AC_TEMPERATURE_CONVERSION
        ]
        == 8
    )

    half_degree = mock_device()
    half_degree["productId"] = f"{'0' * 24}1f620000"
    half_degree["params"] = encode_ac_temperature_command(half_degree, 16.5)
    assert half_degree["params"] == {
        AC_TEMPERATURE_TARGET: 160,
        AC_TEMPERATURE_DECIMAL: 1,
    }
    normalize_device_params(half_degree)
    assert half_degree["params"][AC_TEMPERATURE_TARGET] == 165


def test_v3_heat_pump_tank_temperature_decoder_fails_closed():
    """The verified key-state byte is decoded; malformed values remain unknown."""
    device = mock_heat_pump(ver=3)
    device["params"] = {"key_states": "000044"}
    normalize_device_params(device)
    assert device["params"][HP_HOT_WATER_TANK_TEMPERATURE] == 360
    assert all(
        decode_v3_hp_tank_temp_from_key_states(value) is None
        for value in ("", "00", "zz", "000000", "0000ff")
    )
