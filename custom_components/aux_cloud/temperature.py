"""AUX air-conditioner target-temperature encoding helpers."""

from decimal import Decimal, ROUND_HALF_UP

from .api.const import (
    AC_TEMPERATURE_CONVERT,
    AC_TEMPERATURE_TARGET,
    AC_TEMPERATURE_UNIT,
)


AUX_TEMPERATURE_UNIT_FAHRENHEIT = 2


def decode_ac_target_temperature(params: dict) -> float | None:
    """Decode an AUX target temperature into the device's native unit.

    Fahrenheit-mode AUX units split their Celsius-tenths representation across
    ``temp`` and ``ac_tempconvert``. The physical unit and AC Freedom display
    the nearest whole Fahrenheit degree represented by that pair.
    """
    raw_temp = params.get(AC_TEMPERATURE_TARGET)
    if raw_temp is None:
        return None

    if params.get(AC_TEMPERATURE_UNIT) != AUX_TEMPERATURE_UNIT_FAHRENHEIT:
        return raw_temp / 10

    # AUX may return a non-zero ones digit in ``temp``. AC Freedom discards it
    # before appending ``ac_tempconvert``.
    converted_tenths_celsius = (
        (int(raw_temp) // 10) * 10
        + int(params.get(AC_TEMPERATURE_CONVERT, 0) or 0)
    )

    # Exact positive-number equivalent of AC Freedom's HALF_UP rounding of
    # (C * 1.8) + 32, without introducing binary floating-point edge cases.
    return 32 + (converted_tenths_celsius * 9 + 25) // 50


def encode_ac_target_temperature(temperature: float, temp_unit: int | None) -> dict:
    """Encode a target in the device's native unit using AUX's wire format."""
    if temp_unit != AUX_TEMPERATURE_UNIT_FAHRENHEIT:
        # Celsius-mode devices advertise whole-degree setpoints.
        return {AC_TEMPERATURE_TARGET: round(temperature) * 10}

    fahrenheit = int(
        Decimal(str(temperature)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )

    # This mirrors AC Freedom: convert the selected integer Fahrenheit value
    # to tenths Celsius with RoundingMode.DOWN, then split the final digit into
    # ac_tempconvert.
    converted_tenths_celsius = (fahrenheit - 32) * 50 // 9
    raw_temp = (converted_tenths_celsius // 10) * 10
    temp_convert = converted_tenths_celsius % 10

    return {
        AC_TEMPERATURE_UNIT: AUX_TEMPERATURE_UNIT_FAHRENHEIT,
        AC_TEMPERATURE_TARGET: raw_temp,
        AC_TEMPERATURE_CONVERT: temp_convert,
    }
