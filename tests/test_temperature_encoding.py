"""Tests for AUX air-conditioner target-temperature encoding."""

import pytest

from custom_components.aux_cloud.api.const import (
    AC_TEMPERATURE_CONVERT,
    AC_TEMPERATURE_TARGET,
    AC_TEMPERATURE_UNIT,
)
from custom_components.aux_cloud.temperature import (
    decode_ac_target_temperature,
    encode_ac_target_temperature,
)


@pytest.mark.parametrize(
    ("fahrenheit", "raw_temp", "temp_convert"),
    [
        (72, 220, 0),
        (73, 220, 7),
        (74, 230, 2),
        (75, 230, 7),
        (76, 240, 2),
        (77, 250, 0),
        (78, 255, 5),
    ],
)
def test_decode_captured_fahrenheit_device_values(
    fahrenheit, raw_temp, temp_convert
):
    """Decode values captured after matching AC Freedom/display setpoints."""
    decoded = decode_ac_target_temperature(
        {
            AC_TEMPERATURE_TARGET: raw_temp,
            AC_TEMPERATURE_UNIT: 2,
            AC_TEMPERATURE_CONVERT: temp_convert,
        }
    )

    assert decoded == fahrenheit


@pytest.mark.parametrize(
    ("fahrenheit", "raw_temp", "temp_convert"),
    [
        (72, 220, 2),
        (73, 220, 7),
        (74, 230, 3),
        (75, 230, 8),
        (76, 240, 4),
        (77, 250, 0),
        (78, 250, 5),
    ],
)
def test_encode_fahrenheit_matches_ac_freedom(
    fahrenheit, raw_temp, temp_convert
):
    """Mirror AC Freedom's DOWN-rounded split wire representation."""
    assert encode_ac_target_temperature(fahrenheit, 2) == {
        AC_TEMPERATURE_UNIT: 2,
        AC_TEMPERATURE_TARGET: raw_temp,
        AC_TEMPERATURE_CONVERT: temp_convert,
    }


def test_celsius_device_encoding_is_unchanged():
    """Keep the existing whole-Celsius behavior for non-Fahrenheit devices."""
    assert encode_ac_target_temperature(23.3, 1) == {
        AC_TEMPERATURE_TARGET: 230
    }
    assert decode_ac_target_temperature(
        {AC_TEMPERATURE_TARGET: 235, AC_TEMPERATURE_UNIT: 1}
    ) == 23.5


def test_missing_target_temperature_decodes_to_none():
    assert decode_ac_target_temperature({AC_TEMPERATURE_UNIT: 2}) is None
