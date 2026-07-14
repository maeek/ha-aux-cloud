"""AUX product profiles and parameter capability rules."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

from ..api.models import AuxDevice
from ..api.protocol.common import decode_device_cookie

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

AC_MODE_COOLING = 0
AC_MODE_HEATING = 1
AC_MODE_DRY = 2
AC_MODE_FAN = 3
AC_MODE_AUTO = 4

AC_SWING_VERTICAL = "ac_vdir"
AC_SWING_VERTICAL_ON = {AC_SWING_VERTICAL: 1}
AC_SWING_VERTICAL_OFF = {AC_SWING_VERTICAL: 0}

AC_SWING_HORIZONTAL = "ac_hdir"
AC_SWING_HORIZONTAL_ON = {AC_SWING_HORIZONTAL: 1}
AC_SWING_HORIZONTAL_OFF = {AC_SWING_HORIZONTAL: 0}

AC_AUXILIARY_HEAT = "ac_astheat"

AC_CLEAN = "ac_clean"

AC_HEALTH = "ac_health"

AC_CHILD_LOCK = "childlock"

AC_COMFORTABLE_WIND = "comfwind"

AC_MILDEW_PROOF = "mldprf"

AC_SLEEP = "ac_slp"

AC_SCREEN_DISPLAY = "scrdisp"

AC_POWER_LIMIT = "pwrlimit"
AC_POWER_LIMIT_SWITCH = "pwrlimitswitch"

# This is a special parameter that allows for fetching envtemp from the AC.
AC_MODE_SPECIAL = "mode"

AC_FAN_SPEED = "ac_mark"
AC_FAN_AUTO = 0
AC_FAN_LOW = 1
AC_FAN_MEDIUM = 2
AC_FAN_HIGH = 3
AC_FAN_TURBO = 4
AC_FAN_MUTE = 5
AC_FAN_MEDIUM_LOW = 6
AC_FAN_MEDIUM_HIGH = 7


# Heat Pump constants
HP_MODE_COOLING = 1
HP_MODE_HEATING = 4

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

AUX_PROTOCOL_VERSION: Final = "_aux_protocol_version"
AUX_QUERY_FAILURES: Final = "_aux_query_failures"
_MAX_COOKIE_PROFILE_PARAMS: Final = 512
_MAX_COOKIE_PARAM_LENGTH: Final = 128

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


# pylint: disable=too-many-instance-attributes
@dataclass(frozen=True, slots=True)
class ProductProfile:
    """Capabilities and quirks for an AUX product family."""

    product_ids: tuple[str, ...]
    model_name: str
    params: tuple[str, ...]
    special_params: tuple[str, ...] = ()
    device_type: Literal["ac", "heat_pump", "unknown"] = "unknown"
    writable_params: tuple[str, ...] = ()
    hvac_modes: tuple[int, ...] = ()
    fan_speeds: tuple[int, ...] = ()
    horizontal_swing: bool = False
    vertical_swing: bool = False
    half_degree_via_flag: bool = False

    def initial_param_queries(self, _device: AuxDevice) -> list[list[str]]:
        """Return HTTP parameter query batches used during device bootstrap."""
        if self.device_type == "unknown":
            return []
        if self.special_params:
            return [[], list(self.special_params)]
        return [[]]

    def prepare_command(
        self,
        _device: AuxDevice,
        params: list[str],
        vals: list[Any],
    ) -> tuple[list[str], list[Any]]:
        """Apply product-specific command adjustments before transport serialization."""
        return list(params), list(vals)

    def fallback_param_queries(self, _device: AuxDevice) -> list[list[str]]:
        """Return alternate bootstrap queries after an unsupported primary GET."""
        return []

    def invalid_command_parameter(self, values: Mapping[str, Any]) -> str | None:
        """Return the first command parameter or value this profile rejects."""
        for param in values:
            if param not in self.writable_params:
                return param
        if self.device_type == "ac":
            return _invalid_ac_command_parameter(self, values)
        return None


class HeatPumpProfile(ProductProfile):
    """AUX heat-pump profile with v3-specific command and bootstrap rules."""

    def initial_param_queries(self, device: AuxDevice) -> list[list[str]]:
        """Return heat-pump bootstrap query batches."""
        if is_v3_heat_pump(device):
            return [list(query) for query in V3_HEAT_PUMP_QUERIES]
        return [[], list(self.special_params)]

    def prepare_command(
        self,
        device: AuxDevice,
        params: list[str],
        vals: list[Any],
    ) -> tuple[list[str], list[Any]]:
        """Append the v3 heat-pump version marker required by AUX set commands."""
        prepared_params = list(params)
        prepared_vals = list(vals)
        version = get_protocol_version(device)
        if version is not None and version >= 3 and "ver" not in prepared_params:
            prepared_params.append("ver")
            prepared_vals.append([{"idx": 1, "val": version}])
        return prepared_params, prepared_vals

    def fallback_param_queries(self, device: AuxDevice) -> list[list[str]]:
        """Return the versioned bootstrap required by newer heat pumps."""
        if is_v3_heat_pump(device):
            return []
        return [list(query) for query in V3_HEAT_PUMP_QUERIES]


def _ac_profile(
    product_ids: tuple[str, ...],
    *,
    model_name: str = "AUX Air Conditioner",
    params: tuple[str, ...] = AC_PARAMS,
    hvac_modes: tuple[int, ...] = STANDARD_AC_MODES,
    fan_speeds: tuple[int, ...] = STANDARD_FAN_SPEEDS,
    horizontal_swing: bool = True,
    vertical_swing: bool = True,
    half_degree_via_flag: bool = False,
) -> ProductProfile:
    """Build an AC profile from shared capabilities and explicit deviations."""
    return ProductProfile(
        product_ids=product_ids,
        model_name=model_name,
        params=params,
        special_params=AC_SPECIAL_PARAMS,
        device_type="ac",
        writable_params=tuple(param for param in AC_WRITABLE_PARAMS if param in params),
        hvac_modes=hvac_modes,
        fan_speeds=fan_speeds,
        horizontal_swing=horizontal_swing,
        vertical_swing=vertical_swing,
        half_degree_via_flag=half_degree_via_flag,
    )


STANDARD_AC_PROFILE = _ac_profile(STANDARD_AC_PRODUCT_IDS)
TEMPDEC_AC_PROFILE = _ac_profile(
    TEMPDEC_AC_PRODUCT_IDS,
    half_degree_via_flag=True,
)
EXTENDED_FAN_AC_PROFILE = _ac_profile(
    EXTENDED_FAN_AC_PRODUCT_IDS,
    hvac_modes=NO_AUTO_AC_MODES,
    fan_speeds=EXTENDED_FAN_SPEEDS,
)
VRV_AC_PROFILE = _ac_profile(
    VRV_AC_PRODUCT_IDS,
    model_name="AUX VRV Air Conditioner",
    fan_speeds=VRV_FAN_SPEEDS,
    horizontal_swing=False,
)
MULTI_SPLIT_AC_PROFILE = _ac_profile(
    MULTI_SPLIT_AC_PRODUCT_IDS,
    model_name="AUX Multi-split Air Conditioner",
    params=MULTI_SPLIT_PARAMS,
    hvac_modes=NO_AUTO_AC_MODES,
    fan_speeds=EXTENDED_FAN_SPEEDS,
    half_degree_via_flag=True,
)
SUBDEVICE_AC_PROFILE = _ac_profile(
    SUBDEVICE_AC_PRODUCT_IDS,
    model_name="AUX Air Conditioner Sub-device",
    params=SUBDEVICE_PARAMS,
    hvac_modes=NO_AUTO_AC_MODES,
    fan_speeds=EXTENDED_FAN_SPEEDS,
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
PROFILE_BY_PRODUCT_ID = {
    product_id: profile
    for profile in PRODUCT_PROFILES
    for product_id in profile.product_ids
}


def get_product_profile(product_id: str | None) -> ProductProfile:
    """Return the product profile for a product ID."""
    if product_id is None:
        return DEFAULT_PROFILE
    return PROFILE_BY_PRODUCT_ID.get(product_id, DEFAULT_PROFILE)


def get_protocol_version(device: Mapping[str, Any]) -> int | None:
    """Return the effective device protocol version without guessing."""
    return get_protocol_version_details(device)[0]


def get_protocol_version_details(
    device: Mapping[str, Any],
) -> tuple[int | None, str | None]:
    """Resolve protocol metadata and identify its non-sensitive source."""
    # A session value is populated only after a device response confirms that
    # extern/cookie metadata is stale. That direct observation must win thereafter.
    if version := _positive_version(device.get(AUX_PROTOCOL_VERSION)):
        return version, "session"

    external = _json_mapping(device.get("extern"))
    if external is not None and (version := _positive_version(external.get("ver"))):
        return version, "extern"

    cookie = decode_device_cookie(device.get("cookie"))
    extend = _json_mapping(cookie.get("extend")) if cookie is not None else None
    if extend is not None and (version := _positive_version(extend.get("ver"))):
        return version, "cookie_extend"

    params = device.get("params")
    if isinstance(params, Mapping) and (
        version := _positive_version(params.get("ver"))
    ):
        return version, "response"
    return None, None


def get_cookie_profile_params(device: Mapping[str, Any]) -> tuple[str, ...]:
    """Return bounded product-interface names embedded in a device cookie."""
    cookie = decode_device_cookie(device.get("cookie"))
    profile = _json_mapping(cookie.get("profile")) if cookie is not None else None
    if profile is None:
        return ()
    suids = profile.get("suids")
    if not isinstance(suids, list):
        return ()

    params: set[str] = set()
    for suid in suids:
        if not isinstance(suid, Mapping):
            continue
        interfaces = suid.get("intfs")
        if not isinstance(interfaces, Mapping):
            continue
        for param in interfaces:
            if isinstance(param, str) and 0 < len(param) <= _MAX_COOKIE_PARAM_LENGTH:
                params.add(param)
                if len(params) > _MAX_COOKIE_PROFILE_PARAMS:
                    return ()
    return tuple(sorted(params))


def _json_mapping(value: Any) -> Mapping[str, Any] | None:
    """Return a JSON object supplied either directly or as encoded text."""
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _positive_version(value: Any) -> int | None:
    """Return a positive integral numeric protocol version."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)
    return None


def set_protocol_version(device: AuxDevice, version: Any) -> None:
    """Store a successfully resolved protocol version on the runtime snapshot."""
    if resolved := _positive_version(version):
        device[AUX_PROTOCOL_VERSION] = resolved


def _invalid_ac_command_parameter(
    profile: ProductProfile, values: Mapping[str, Any]
) -> str | None:
    """Return the first invalid AC-specific command value."""
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


def encode_ac_temperature_command(
    device: AuxDevice, temperature_c: float
) -> dict[str, int]:
    """Encode a logical Celsius target using the AC Freedom wire format."""
    profile = get_product_profile(device.get("productId"))
    current_params = device.get("params", {})
    if current_params.get(AC_TEMPERATURE_UNIT) == 2:
        # AC Freedom truncates the Celsius conversion of Fahrenheit targets.
        target_x10 = int(temperature_c * 10)
        base = (target_x10 // 10) * 10
        return {
            AC_TEMPERATURE_TARGET: base,
            AC_TEMPERATURE_UNIT: 2,
            AC_TEMPERATURE_DECIMAL: 0,
            AC_TEMPERATURE_CONVERSION: target_x10 - base,
        }

    target_x10 = round(temperature_c * 10)
    if profile.half_degree_via_flag:
        base = (target_x10 // 10) * 10
        return {
            AC_TEMPERATURE_TARGET: base,
            AC_TEMPERATURE_DECIMAL: int(target_x10 - base >= 5),
        }

    return {AC_TEMPERATURE_TARGET: target_x10}


def is_v3_heat_pump(device: Mapping[str, Any]) -> bool:
    """Determine if a device is a v3 or later heat pump based on its metadata."""
    version = get_protocol_version(device)
    return bool(
        version is not None
        and version >= 3
        and device.get("productId") in HEAT_PUMP_PRODUCT_IDS
    )
