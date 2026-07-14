"""Focused AUX Cloud tests."""

import json

import pytest

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

from .api_helpers import mock_cookie as _mock_cookie
from .api_helpers import mock_device as _mock_device
from .api_helpers import mock_heat_pump as _mock_heat_pump


class TestAuxCloudAPI:
    """Tests for the AuxCloudAPI class."""

    def test_ac_profile_initial_queries_and_supported_params(self):
        """Test AC profile exposes bootstrap and entity capability params."""
        device = _mock_device()

        profile = get_product_profile(device["productId"])
        assert profile.initial_param_queries(device) == [[], [AC_MODE_SPECIAL]]
        assert AC_POWER in profile.params
        assert profile.special_params == (AC_MODE_SPECIAL,)

    def test_heat_pump_profile_initial_queries(self):
        """Test heat-pump profile owns v2/v3 bootstrap query differences."""
        v2_device = _mock_heat_pump(ver=2)
        assert get_product_profile(v2_device["productId"]).initial_param_queries(
            v2_device
        ) == [
            [],
            [HP_HOT_WATER_TANK_TEMPERATURE],
        ]
        v3_device = _mock_heat_pump(ver=3)
        assert get_product_profile(v3_device["productId"]).initial_param_queries(
            v3_device
        ) == [list(query) for query in V3_HEAT_PUMP_QUERIES]

    def test_heat_pump_version_prefers_extern_over_cookie_extend(self):
        """Test app-compatible extern metadata wins over cookie metadata."""
        device = _mock_heat_pump(ver=4)
        device["cookie"] = _mock_cookie(extend=json.dumps({"ver": 2}))

        assert get_protocol_version(device) == 4
        assert get_protocol_version_details(device) == (4, "extern")
        assert get_product_profile(device["productId"]).initial_param_queries(
            device
        ) == [list(query) for query in V3_HEAT_PUMP_QUERIES]

    def test_heat_pump_version_uses_cookie_extend_without_extern(self):
        """Test cookie extend metadata selects v3 when extern is unavailable."""
        device = _mock_heat_pump()
        device.pop("extern")
        device["cookie"] = _mock_cookie(extend=json.dumps({"ver": 3}))

        assert get_protocol_version(device) == 3
        assert get_protocol_version_details(device) == (3, "cookie_extend")
        assert get_product_profile(device["productId"]).initial_param_queries(
            device
        ) == [list(query) for query in V3_HEAT_PUMP_QUERIES]

    def test_confirmed_session_version_overrides_metadata_proven_stale(self):
        """Test a direct device response prevents repeated legacy probes."""
        device = _mock_heat_pump(ver=2)
        device["cookie"] = _mock_cookie(extend={"ver": 2})
        device[AUX_PROTOCOL_VERSION] = 4

        assert get_protocol_version(device) == 4
        assert get_protocol_version_details(device) == (4, "session")

    @pytest.mark.parametrize(
        ("extern", "cookie_metadata"),
        [
            ("not-json", "not-base64"),
            (json.dumps({"ver": True}), {"extend": {"ver": 3.5}}),
            (json.dumps({"ver": "3"}), {"extend": {"ver": "3"}}),
        ],
    )
    def test_malformed_protocol_metadata_uses_legacy_plan(
        self, extern, cookie_metadata
    ):
        """Test malformed metadata is ignored instead of guessed."""
        device = _mock_heat_pump()
        device["extern"] = extern
        device["cookie"] = (
            cookie_metadata
            if isinstance(cookie_metadata, str)
            else _mock_cookie(**cookie_metadata)
        )

        assert get_protocol_version(device) is None
        assert get_product_profile(device["productId"]).initial_param_queries(
            device
        ) == [[], [HP_HOT_WATER_TANK_TEMPERATURE]]

    def test_cookie_profile_interfaces_are_diagnostic_only(self):
        """Test bounded cookie interfaces can be inspected without affecting quirks."""
        device = _mock_heat_pump(ver=2)
        device["cookie"] = _mock_cookie(
            profile={
                "suids": [
                    {"intfs": {"hp_pwr": [], "hp_water_tank_temp": []}},
                    {"intfs": {"diagnostic_only": []}},
                ]
            }
        )

        assert get_cookie_profile_params(device) == (
            "diagnostic_only",
            "hp_pwr",
            "hp_water_tank_temp",
        )
        assert get_product_profile(device["productId"]).initial_param_queries(
            device
        ) == [[], [HP_HOT_WATER_TANK_TEMPERATURE]]

    def test_unknown_profile_has_no_speculative_query_plan(self):
        """Test unsupported products never inherit a generic empty GET."""
        profile = get_product_profile("unknown-product")

        assert profile.initial_param_queries(_mock_device()) == []
        assert profile.fallback_param_queries(_mock_device()) == []

    def test_heat_pump_command_includes_resolved_protocol_version(self):
        """Test heat-pump commands include the negotiated protocol version."""
        device = _mock_heat_pump(ver=4)
        params, vals = get_product_profile(device["productId"]).prepare_command(
            device,
            ["hp_pwr"],
            [[{"idx": 1, "val": 1}]],
        )

        assert params == ["hp_pwr", "ver"]
        assert vals[-1] == [{"idx": 1, "val": 4}]

    @pytest.mark.parametrize(
        ("suffix", "auto_mode", "extended_fan", "horizontal_swing", "power_limit"),
        [
            ("28620000", False, True, True, True),
            ("45620000", False, True, True, False),
            ("56ac0000", True, False, False, True),
            ("a44e0000", True, False, False, True),
            ("c5510000", False, True, True, True),
            ("c9100100", False, True, True, False),
        ],
    )
    def test_apk_product_profile_constraints(
        self, suffix, auto_mode, extended_fan, horizontal_swing, power_limit
    ):
        """Test product-specific controls match verified AC Freedom behavior."""
        profile = get_product_profile(f"{'0' * 24}{suffix}")

        assert (4 in profile.hvac_modes) is auto_mode
        assert (6 in profile.fan_speeds and 7 in profile.fan_speeds) is extended_fan
        assert profile.horizontal_swing is horizontal_swing
        assert (AC_POWER_LIMIT in profile.writable_params) is power_limit

    def test_ac_temperature_wire_formats_and_normalization(self):
        """Test standard, Fahrenheit, and half-degree AC wire formats."""
        standard = _mock_device()
        assert encode_ac_temperature_command(standard, 16.5) == {
            AC_TEMPERATURE_TARGET: 165
        }

        fahrenheit = _mock_device()
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

        # AC Freedom truncates, rather than rounds, converted Fahrenheit targets.
        assert encode_ac_temperature_command(fahrenheit, (66 - 32) / 1.8) == {
            AC_TEMPERATURE_TARGET: 180,
            AC_TEMPERATURE_UNIT: 2,
            AC_TEMPERATURE_DECIMAL: 0,
            AC_TEMPERATURE_CONVERSION: 8,
        }

        half_degree = _mock_device()
        half_degree["productId"] = f"{'0' * 24}1f620000"
        encoded = encode_ac_temperature_command(half_degree, 16.5)
        assert encoded == {
            AC_TEMPERATURE_TARGET: 160,
            AC_TEMPERATURE_DECIMAL: 1,
        }
        half_degree["params"] = encoded
        normalize_device_params(half_degree)
        assert half_degree["params"][AC_TEMPERATURE_TARGET] == 165

    def test_v3_heat_pump_tank_temperature_normalizer(self):
        """Test v3 heat-pump key_states tank temperature normalization."""
        device = _mock_heat_pump(ver=3)
        device["params"] = {"key_states": "000044"}

        normalize_device_params(device)

        assert device["params"][HP_HOT_WATER_TANK_TEMPERATURE] == 360

    @pytest.mark.parametrize("payload", ("", "00", "zz", "000000", "0000ff"))
    def test_v3_heat_pump_tank_temperature_rejects_malformed_values(self, payload):
        """Test malformed and implausible key-state temperatures stay unknown."""
        assert decode_v3_hp_tank_temp_from_key_states(payload) is None
