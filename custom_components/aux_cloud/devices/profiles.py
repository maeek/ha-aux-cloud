"""AUX product profiles and parameter capability rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import auto
from typing import Any

# Common constants
AUX_MODE = "ac_mode"

AUX_ECOMODE = "ecomode"
AUX_ECOMODE_OFF = {AUX_ECOMODE: 0}
AUX_ECOMODE_ON = {AUX_ECOMODE: 1}
AUX_ERROR_FLAG = "err_flag"

# AC constants
AC_POWER = "pwr"
AC_POWER_OFF = {AC_POWER: 0}
AC_POWER_ON = {AC_POWER: 1}

AC_TEMPERATURE_TARGET = "temp"
AC_TEMPERATURE_AMBIENT = "envtemp"
AC_TEMPERATURE_UNIT = "tempunit"
AC_TEMPERATURE_DECIMAL = "ac_tempdec"
AC_TEMPERATURE_CONVERSION = "ac_tempconvert"

AC_MODE_COOLING = {AUX_MODE: 0}
AC_MODE_HEATING = {AUX_MODE: 1}
AC_MODE_DRY = {AUX_MODE: 2}
AC_MODE_FAN = {AUX_MODE: 3}
AC_MODE_AUTO = {AUX_MODE: 4}

AC_SWING_VERTICAL = "ac_vdir"
AC_SWING_VERTICAL_ON = {AC_SWING_VERTICAL: 1}
AC_SWING_VERTICAL_OFF = {AC_SWING_VERTICAL: 0}

AC_SWING_HORIZONTAL = "ac_hdir"
AC_SWING_HORIZONTAL_ON = {AC_SWING_HORIZONTAL: 1}
AC_SWING_HORIZONTAL_OFF = {AC_SWING_HORIZONTAL: 0}

AC_AUXILIARY_HEAT = "ac_astheat"
AC_AUXILIARY_HEAT_OFF = {AC_AUXILIARY_HEAT: 0}
AC_AUXILIARY_HEAT_ON = {AC_AUXILIARY_HEAT: 1}

AC_CLEAN = "ac_clean"
AC_CLEAN_OFF = {AC_CLEAN: 0}
AC_CLEAN_ON = {AC_CLEAN: 1}

AC_HEALTH = "ac_health"
AC_HEALTH_OFF = {AC_HEALTH: 0}
AC_HEALTH_ON = {AC_HEALTH: 1}

AC_CHILD_LOCK = "childlock"
AC_CHILD_LOCK_OFF = {AC_CHILD_LOCK: 0}
AC_CHILD_LOCK_ON = {AC_CHILD_LOCK: 1}

AC_COMFORTABLE_WIND = "comfwind"
AC_COMFORTABLE_WIND_OFF = {AC_COMFORTABLE_WIND: 0}
AC_COMFORTABLE_WIND_ON = {AC_COMFORTABLE_WIND: 1}

AC_MILDEW_PROOF = "mldprf"
AC_MILDEW_PROOF_OFF = {AC_MILDEW_PROOF: 0}
AC_MILDEW_PROOF_ON = {AC_MILDEW_PROOF: 1}

AC_SLEEP = "ac_slp"
AC_SLEEP_OFF = {AC_SLEEP: 0}
AC_SLEEP_ON = {AC_SLEEP: 1}

AC_SCREEN_DISPLAY = "scrdisp"
AC_SCREEN_DISPLAY_OFF = {AC_SCREEN_DISPLAY: 0}
AC_SCREEN_DISPLAY_ON = {AC_SCREEN_DISPLAY: 1}

AC_POWER_LIMIT = "pwrlimit"
AC_POWER_LIMIT_SWITCH = "pwrlimitswitch"
AC_POWER_LIMIT_OFF = {AC_POWER_LIMIT: 0}
AC_POWER_LIMIT_ON = {AC_POWER_LIMIT: 1}

# This is a special parameter that allows for fetching envtemp from the AC.
AC_MODE_SPECIAL = "mode"

AC_FAN_SPEED = "ac_mark"


class ACFanSpeed(auto):
    PARAM_NAME = "ac_mark"

    """Fan speed levels for AUX air conditioners."""

    AUTO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    TURBO = 4
    MUTE = 5
    MEDIUM_LOW = 6
    MEDIUM_HIGH = 7


# Heat Pump constants
HP_MODE_AUTO = {AUX_MODE: 0}
HP_MODE_COOLING = {AUX_MODE: 1}
HP_MODE_HEATING = {AUX_MODE: 4}

HP_HEATER_POWER = "ac_pwr"
HP_HEATER_POWER_OFF = {HP_HEATER_POWER: 0}
HP_HEATER_POWER_ON = {HP_HEATER_POWER: 1}

HP_HEATER_TEMPERATURE_TARGET = "ac_temp"

HP_HEATER_AUTO_WATER_TEMP = "hp_auto_wtemp"
"""
Auto water temperature control for heat pump.
    0 - Off
    1...8 - Predefined controls
    9 - User defined control - set manually on heat pump
"""

HP_WATER_POWER = "hp_pwr"
HP_WATER_POWER_OFF = {HP_WATER_POWER: 0}
HP_WATER_POWER_ON = {HP_WATER_POWER: 1}

HP_QUIET_MODE = "qtmode"

HP_HOT_WATER_TANK_TEMPERATURE = "hp_water_tank_temp"
HP_HOT_WATER_TEMPERATURE_TARGET = "hp_hotwater_temp"

HP_WATER_FAST_HOTWATER = "hp_fast_hotwater"
HP_WATER_FAST_HOTWATER_ON = {HP_WATER_FAST_HOTWATER: 1}
HP_WATER_FAST_HOTWATER_OFF = {HP_WATER_FAST_HOTWATER: 0}

AC_PRODUCT_IDS = (
    "000000000000000000000000c0620000",
    "0000000000000000000000002a4e0000",
    "0000000000000000000000001f620000",
    "00000000000000000000000028620000",
    "00000000000000000000000045620000",
    "00000000000000000000000056ac0000",
    "0000000000000000000000007faf0000",
    "00000000000000000000000082af0000",
    "000000000000000000000000a44e0000",
    "000000000000000000000000c5510000",
    "000000000000000000000000c9100100",
)
HEAT_PUMP_PRODUCT_IDS = ("000000000000000000000000c3aa0000",)

STANDARD_AC_PRODUCT_IDS = (
    "000000000000000000000000c0620000",
    "0000000000000000000000002a4e0000",
    "0000000000000000000000007faf0000",
    "00000000000000000000000082af0000",
)
TEMPDEC_AC_PRODUCT_IDS = ("0000000000000000000000001f620000",)
EXTENDED_FAN_AC_PRODUCT_IDS = (
    "00000000000000000000000028620000",
    "000000000000000000000000c5510000",
)
VRV_AC_PRODUCT_IDS = (
    "00000000000000000000000056ac0000",
    "000000000000000000000000a44e0000",
)
MULTI_SPLIT_AC_PRODUCT_IDS = ("00000000000000000000000045620000",)
SUBDEVICE_AC_PRODUCT_IDS = ("000000000000000000000000c9100100",)

AUX_PROTOCOL_VERSION = "_aux_protocol_version"
AUX_QUERY_FAILURES = "_aux_query_failures"

AC_PARAMS = (
    AC_AUXILIARY_HEAT,
    AC_CLEAN,
    AC_SWING_HORIZONTAL,
    AC_HEALTH,
    AC_FAN_SPEED,
    AUX_MODE,
    AC_SLEEP,
    AC_SWING_VERTICAL,
    AUX_ECOMODE,
    AUX_ERROR_FLAG,
    AC_MILDEW_PROOF,
    AC_POWER,
    AC_SCREEN_DISPLAY,
    AC_TEMPERATURE_TARGET,
    AC_TEMPERATURE_AMBIENT,
    AC_POWER_LIMIT,
    AC_POWER_LIMIT_SWITCH,
    AC_CHILD_LOCK,
    AC_COMFORTABLE_WIND,
    "new_type",
    AC_TEMPERATURE_CONVERSION,
    AC_TEMPERATURE_DECIMAL,
    "sleepdiy",
    "ac_errcode1",
    AC_TEMPERATURE_UNIT,
    "tenelec",
)
AC_SPECIAL_PARAMS = (AC_MODE_SPECIAL,)

HP_PARAMS = (
    "ac_errcode1",
    AUX_MODE,
    HP_HEATER_POWER,
    HP_HEATER_TEMPERATURE_TARGET,
    AUX_ECOMODE,
    AUX_ERROR_FLAG,
    HP_HEATER_AUTO_WATER_TEMP,
    HP_WATER_FAST_HOTWATER,
    HP_HOT_WATER_TEMPERATURE_TARGET,
    HP_WATER_POWER,
    HP_QUIET_MODE,
)
HP_SPECIAL_PARAMS = (HP_HOT_WATER_TANK_TEMPERATURE,)

MULTI_SPLIT_PARAMS = tuple(
    param for param in AC_PARAMS if param not in {AC_POWER_LIMIT, AC_POWER_LIMIT_SWITCH}
)
SUBDEVICE_PARAMS = (
    AC_FAN_SPEED,
    AUX_MODE,
    AC_POWER,
    AC_SCREEN_DISPLAY,
    AC_SWING_HORIZONTAL,
    AC_SWING_VERTICAL,
    AC_TEMPERATURE_AMBIENT,
    AC_TEMPERATURE_TARGET,
    AC_TEMPERATURE_UNIT,
    AC_TEMPERATURE_DECIMAL,
    AC_TEMPERATURE_CONVERSION,
)

AC_WRITABLE_PARAMS = (
    AC_AUXILIARY_HEAT,
    AC_CHILD_LOCK,
    AC_CLEAN,
    AC_COMFORTABLE_WIND,
    AC_FAN_SPEED,
    AC_HEALTH,
    AC_MILDEW_PROOF,
    AC_POWER,
    AC_POWER_LIMIT,
    AC_POWER_LIMIT_SWITCH,
    AC_SCREEN_DISPLAY,
    AC_SLEEP,
    AC_SWING_HORIZONTAL,
    AC_SWING_VERTICAL,
    AC_TEMPERATURE_CONVERSION,
    AC_TEMPERATURE_DECIMAL,
    AC_TEMPERATURE_TARGET,
    AC_TEMPERATURE_UNIT,
    AUX_ECOMODE,
    AUX_MODE,
)
HP_WRITABLE_PARAMS = (
    AUX_ECOMODE,
    AUX_MODE,
    HP_HEATER_AUTO_WATER_TEMP,
    HP_HEATER_POWER,
    HP_HEATER_TEMPERATURE_TARGET,
    HP_HOT_WATER_TEMPERATURE_TARGET,
    HP_QUIET_MODE,
    HP_WATER_FAST_HOTWATER,
    HP_WATER_POWER,
)

STANDARD_AC_MODES = (0, 1, 2, 3, 4)
NO_AUTO_AC_MODES = (0, 1, 2, 3)
STANDARD_FAN_SPEEDS = (0, 1, 2, 3, 4, 5)
EXTENDED_FAN_SPEEDS = (0, 1, 6, 2, 7, 3, 4, 5)
VRV_FAN_SPEEDS = (1, 2, 3)

V3_HEAT_PUMP_QUERIES = (
    ("ver",),
    ("ver", "key_states", "common_states"),
    ("ver", "hp_auto_wtemp", "water_tank_dif", "eco"),
    ("ver", "mute"),
)


@dataclass(frozen=True)
class ProductProfile:
    """Capabilities and quirks for an AUX product family."""

    product_ids: tuple[str, ...]
    model_name: str
    params: tuple[str, ...]
    special_params: tuple[str, ...] = ()
    device_type: str = "unknown"
    writable_params: tuple[str, ...] = ()
    hvac_modes: tuple[int, ...] = ()
    fan_speeds: tuple[int, ...] = ()
    horizontal_swing: bool = False
    vertical_swing: bool = False
    half_degree_via_flag: bool = False

    def matches(self, product_id: str | None) -> bool:
        """Return whether this profile supports a product ID."""
        return product_id in self.product_ids

    def initial_param_queries(self, _device: dict) -> list[list[str]]:
        """Return HTTP parameter query batches used during device bootstrap."""
        if self.special_params:
            return [[], list(self.special_params)]
        return [[]]

    def prepare_command(
        self,
        device: dict,  # pylint: disable=unused-argument
        act: str,  # pylint: disable=unused-argument
        params: list[str],
        vals: list,
    ) -> tuple[list[str], list]:
        """Apply product-specific command adjustments before transport serialization."""
        return list(params), list(vals)


class HeatPumpProfile(ProductProfile):
    """AUX heat-pump profile with v3-specific command and bootstrap rules."""

    def initial_param_queries(self, device: dict) -> list[list[str]]:
        """Return heat-pump bootstrap query batches."""
        if is_v3_heat_pump(device):
            return [list(query) for query in V3_HEAT_PUMP_QUERIES]
        return [[], list(self.special_params)]

    def prepare_command(
        self,
        device: dict,
        act: str,
        params: list[str],
        vals: list,
    ) -> tuple[list[str], list]:
        """Append the v3 heat-pump version marker required by AUX set commands."""
        prepared_params = list(params)
        prepared_vals = list(vals)
        version = get_protocol_version(device)
        if (
            version is not None
            and version >= 3
            and act == "set"
            and "ver" not in prepared_params
        ):
            prepared_params.append("ver")
            prepared_vals.append([{"idx": 1, "val": version}])
        return prepared_params, prepared_vals


STANDARD_AC_PROFILE = ProductProfile(
    product_ids=STANDARD_AC_PRODUCT_IDS,
    model_name="AUX Air Conditioner",
    params=AC_PARAMS,
    special_params=AC_SPECIAL_PARAMS,
    device_type="ac",
    writable_params=AC_WRITABLE_PARAMS,
    hvac_modes=STANDARD_AC_MODES,
    fan_speeds=STANDARD_FAN_SPEEDS,
    horizontal_swing=True,
    vertical_swing=True,
)
TEMPDEC_AC_PROFILE = ProductProfile(
    product_ids=TEMPDEC_AC_PRODUCT_IDS,
    model_name="AUX Air Conditioner",
    params=AC_PARAMS,
    special_params=AC_SPECIAL_PARAMS,
    device_type="ac",
    writable_params=AC_WRITABLE_PARAMS,
    hvac_modes=STANDARD_AC_MODES,
    fan_speeds=STANDARD_FAN_SPEEDS,
    horizontal_swing=True,
    vertical_swing=True,
    half_degree_via_flag=True,
)
EXTENDED_FAN_AC_PROFILE = ProductProfile(
    product_ids=EXTENDED_FAN_AC_PRODUCT_IDS,
    model_name="AUX Air Conditioner",
    params=AC_PARAMS,
    special_params=AC_SPECIAL_PARAMS,
    device_type="ac",
    writable_params=AC_WRITABLE_PARAMS,
    hvac_modes=NO_AUTO_AC_MODES,
    fan_speeds=EXTENDED_FAN_SPEEDS,
    horizontal_swing=True,
    vertical_swing=True,
)
VRV_AC_PROFILE = ProductProfile(
    product_ids=VRV_AC_PRODUCT_IDS,
    model_name="AUX VRV Air Conditioner",
    params=AC_PARAMS,
    special_params=AC_SPECIAL_PARAMS,
    device_type="ac",
    writable_params=AC_WRITABLE_PARAMS,
    hvac_modes=STANDARD_AC_MODES,
    fan_speeds=VRV_FAN_SPEEDS,
    vertical_swing=True,
)
MULTI_SPLIT_AC_PROFILE = ProductProfile(
    product_ids=MULTI_SPLIT_AC_PRODUCT_IDS,
    model_name="AUX Multi-split Air Conditioner",
    params=MULTI_SPLIT_PARAMS,
    special_params=AC_SPECIAL_PARAMS,
    device_type="ac",
    writable_params=tuple(
        param for param in AC_WRITABLE_PARAMS if param in MULTI_SPLIT_PARAMS
    ),
    hvac_modes=NO_AUTO_AC_MODES,
    fan_speeds=EXTENDED_FAN_SPEEDS,
    horizontal_swing=True,
    vertical_swing=True,
    half_degree_via_flag=True,
)
SUBDEVICE_AC_PROFILE = ProductProfile(
    product_ids=SUBDEVICE_AC_PRODUCT_IDS,
    model_name="AUX Air Conditioner Sub-device",
    params=SUBDEVICE_PARAMS,
    special_params=AC_SPECIAL_PARAMS,
    device_type="ac",
    writable_params=tuple(
        param for param in AC_WRITABLE_PARAMS if param in SUBDEVICE_PARAMS
    ),
    hvac_modes=NO_AUTO_AC_MODES,
    fan_speeds=EXTENDED_FAN_SPEEDS,
    horizontal_swing=True,
    vertical_swing=True,
    half_degree_via_flag=True,
)
HEAT_PUMP_PROFILE = HeatPumpProfile(
    product_ids=HEAT_PUMP_PRODUCT_IDS,
    model_name="AUX Heat Pump",
    params=HP_PARAMS,
    special_params=HP_SPECIAL_PARAMS,
    device_type="heat_pump",
    writable_params=HP_WRITABLE_PARAMS,
)
DEFAULT_PROFILE = ProductProfile(
    product_ids=(),
    model_name="Unknown",
    params=(),
)

PRODUCT_PROFILES = (
    STANDARD_AC_PROFILE,
    TEMPDEC_AC_PROFILE,
    EXTENDED_FAN_AC_PROFILE,
    VRV_AC_PROFILE,
    MULTI_SPLIT_AC_PROFILE,
    SUBDEVICE_AC_PROFILE,
    HEAT_PUMP_PROFILE,
)


def get_product_profile(product_id: str | None) -> ProductProfile:
    """Return the product profile for a product ID."""
    for profile in PRODUCT_PROFILES:
        if profile.matches(product_id):
            return profile
    return DEFAULT_PROFILE


def get_device_name(product_id: str | None) -> str:
    """Return a display model name for a product ID."""
    return get_product_profile(product_id).model_name


def get_params_list(product_id: str | None) -> list[str] | None:
    """Return supported standard params for a product ID."""
    profile = get_product_profile(product_id)
    return list(profile.params) if profile.params else None


def get_special_params_list(product_id: str | None) -> list[str] | None:
    """Return supported special params for a product ID."""
    profile = get_product_profile(product_id)
    return list(profile.special_params) if profile.special_params else None


def initial_param_queries(device: dict) -> list[list[str]]:
    """Return bootstrap query batches for a device."""
    return get_product_profile(device.get("productId")).initial_param_queries(device)


def prepare_command(
    device: dict, act: str, params: list[str], vals: list
) -> tuple[list[str], list]:
    """Apply product-profile command adjustments."""
    return get_product_profile(device.get("productId")).prepare_command(
        device, act, params, vals
    )


def fallback_param_queries(device: dict) -> list[list[str]]:
    """Return the versioned heat-pump fallback after an unsupported legacy GET."""
    if device.get("productId") not in HEAT_PUMP_PRODUCT_IDS:
        return []
    return [list(query) for query in V3_HEAT_PUMP_QUERIES]


def get_protocol_version(device: dict) -> int | None:
    """Return the resolved device protocol version without guessing."""
    candidates = [
        device.get(AUX_PROTOCOL_VERSION),
        device.get("params", {}).get("ver"),
    ]
    try:
        external: dict[str, Any] = json.loads(device.get("extern", "{}") or "{}")
        candidates.append(external.get("ver"))
    except (json.JSONDecodeError, TypeError):
        pass

    for candidate in candidates:
        if isinstance(candidate, (int, float)) and int(candidate) > 0:
            return int(candidate)
    return None


def set_protocol_version(device: dict, version: Any) -> None:
    """Store a successfully resolved protocol version on the runtime snapshot."""
    if isinstance(version, (int, float)) and int(version) > 0:
        device[AUX_PROTOCOL_VERSION] = int(version)


def invalid_command_parameter(device: dict, values: dict[str, Any]) -> str | None:
    """Return the first unsupported command parameter or value."""
    profile = get_product_profile(device.get("productId"))
    for param in values:
        if param not in profile.writable_params:
            return param

    if profile.device_type == "ac":
        mode = values.get(AUX_MODE)
        if mode is not None and mode not in profile.hvac_modes:
            return AUX_MODE
        fan_speed = values.get(AC_FAN_SPEED)
        if fan_speed is not None and fan_speed not in profile.fan_speeds:
            return AC_FAN_SPEED
        if AC_SWING_HORIZONTAL in values and not profile.horizontal_swing:
            return AC_SWING_HORIZONTAL
        if AC_SWING_VERTICAL in values and not profile.vertical_swing:
            return AC_SWING_VERTICAL
    return None


def encode_ac_temperature_command(device: dict, temperature_c: float) -> dict[str, int]:
    """Encode a logical Celsius target using the AC Freedom wire format."""
    profile = get_product_profile(device.get("productId"))
    target_x10 = round(temperature_c * 10)
    current_params = device.get("params", {})
    if current_params.get(AC_TEMPERATURE_UNIT) == 2:
        base = (target_x10 // 10) * 10
        return {
            AC_TEMPERATURE_TARGET: base,
            AC_TEMPERATURE_UNIT: 2,
            AC_TEMPERATURE_DECIMAL: 0,
            AC_TEMPERATURE_CONVERSION: target_x10 - base,
        }

    if profile.half_degree_via_flag:
        base = (target_x10 // 10) * 10
        return {
            AC_TEMPERATURE_TARGET: base,
            AC_TEMPERATURE_DECIMAL: int(target_x10 - base >= 5),
        }

    return {AC_TEMPERATURE_TARGET: target_x10}


def is_v3_heat_pump(device: dict) -> bool:
    """Determine if a device is a v3 or later heat pump based on its metadata."""
    version = get_protocol_version(device)
    return bool(
        version is not None
        and version >= 3
        and device.get("productId") in HEAT_PUMP_PRODUCT_IDS
    )


class AuxProducts:
    """Backward-compatible product helper namespace."""

    class DeviceType:
        """Backward-compatible product ID groups."""

        AC_GENERIC = list(AC_PRODUCT_IDS)
        HEAT_PUMP = list(HEAT_PUMP_PRODUCT_IDS)

    AC_PARAMS = list(AC_PARAMS)
    AC_SPECIAL_PARAMS = list(AC_SPECIAL_PARAMS)
    HP_PARAMS = list(HP_PARAMS)
    HP_SPECIAL_PARAMS = list(HP_SPECIAL_PARAMS)

    get_device_name = staticmethod(get_device_name)
    get_params_list = staticmethod(get_params_list)
    get_special_params_list = staticmethod(get_special_params_list)
    is_v3_heat_pump = staticmethod(is_v3_heat_pump)
