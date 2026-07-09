"""Device-specific AUX parameter normalization."""

from __future__ import annotations

from .profiles import (
    AC_TEMPERATURE_CONVERSION,
    AC_TEMPERATURE_DECIMAL,
    AC_TEMPERATURE_TARGET,
    AC_TEMPERATURE_UNIT,
    HP_HOT_WATER_TANK_TEMPERATURE,
    get_product_profile,
    is_v3_heat_pump,
)


def decode_v3_hp_tank_temp_from_key_states(key_states_hex: str) -> int | None:
    """Decode v3 heat-pump tank temperature from key_states into x10 Celsius."""
    if not key_states_hex or not isinstance(key_states_hex, str):
        return None

    try:
        raw = bytes.fromhex(key_states_hex)
        if len(raw) < 3:
            return None

        temp_c = raw[2] - 32
        if temp_c < -20 or temp_c > 120:
            return None

        return int(temp_c) * 10
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def normalize_device_params(device: dict) -> None:
    """Normalize decoded params in-place."""
    params = device.get("params", {})
    profile = get_product_profile(device.get("productId"))
    target = params.get(AC_TEMPERATURE_TARGET)
    if profile.device_type == "ac" and isinstance(target, (int, float)):
        base = (int(target) // 10) * 10
        conversion = params.get(AC_TEMPERATURE_CONVERSION)
        if (
            params.get(AC_TEMPERATURE_UNIT) == 2
            and isinstance(conversion, (int, float))
            and 0 <= int(conversion) <= 9
        ):
            params[AC_TEMPERATURE_TARGET] = base + int(conversion)
        elif profile.half_degree_via_flag and params.get(AC_TEMPERATURE_DECIMAL) == 1:
            params[AC_TEMPERATURE_TARGET] = base + 5

    if is_v3_heat_pump(device):
        key_states = params.get("key_states")
        decoded = decode_v3_hp_tank_temp_from_key_states(key_states)
        if decoded is not None:
            params[HP_HOT_WATER_TANK_TEMPERATURE] = decoded
