"""AUX product profiles and parameter capability rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import auto
import json
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
)
HEAT_PUMP_PRODUCT_IDS = ("000000000000000000000000c3aa0000",)

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
    "ac_tempconvert",
    "sleepdiy",
    "ac_errcode1",
    "tempunit",
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


@dataclass(frozen=True)
class ProductProfile:
    """Capabilities and quirks for an AUX product family."""

    product_ids: tuple[str, ...]
    model_name: str
    params: tuple[str, ...]
    special_params: tuple[str, ...] = ()

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
            return [["ver"]]
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
        if is_v3_heat_pump(device) and act == "set" and "ver" not in prepared_params:
            prepared_params.append("ver")
            prepared_vals.append([{"idx": 1, "val": 3}])
        return prepared_params, prepared_vals


AC_PROFILE = ProductProfile(
    product_ids=AC_PRODUCT_IDS,
    model_name="AUX Air Conditioner",
    params=AC_PARAMS,
    special_params=AC_SPECIAL_PARAMS,
)
HEAT_PUMP_PROFILE = HeatPumpProfile(
    product_ids=HEAT_PUMP_PRODUCT_IDS,
    model_name="AUX Heat Pump",
    params=HP_PARAMS,
    special_params=HP_SPECIAL_PARAMS,
)
DEFAULT_PROFILE = ProductProfile(
    product_ids=(),
    model_name="Unknown",
    params=(),
)

PRODUCT_PROFILES = (AC_PROFILE, HEAT_PUMP_PROFILE)


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


def is_v3_heat_pump(device: dict) -> bool:
    """Determine if a device is a v3 or later heat pump based on its metadata."""
    try:
        version: dict[str, Any] = json.loads(device.get("extern", "{}"))
    except json.JSONDecodeError:
        return False

    return (
        version.get("ver", 0) >= 3 and device.get("productId") in HEAT_PUMP_PRODUCT_IDS
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
