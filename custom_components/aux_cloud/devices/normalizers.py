"""Device-specific AUX parameter normalization."""

from __future__ import annotations

from .profiles import HP_HOT_WATER_TANK_TEMPERATURE, is_v3_heat_pump


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
    if is_v3_heat_pump(device):
        key_states = device.get("params", {}).get("key_states")
        decoded = decode_v3_hp_tank_temp_from_key_states(key_states)
        if decoded is not None:
            device["params"][HP_HOT_WATER_TANK_TEMPERATURE] = decoded
