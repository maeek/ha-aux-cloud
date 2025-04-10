from enum import auto

AUX_MODEL_TO_NAME = {
    "000000000000000000000000c3aa0000": "AUX Heat Pump",
    "000000000000000000000000c0620000": "AUX Air Conditioner",
}

AC = "Air Conditioner"
HEAT_PUMP = "Heat Pump"


class AuxProductCategory(auto):
    HEAT_PUMP = ["000000000000000000000000c3aa0000"]

    AC = ["000000000000000000000000c0620000"]


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

# This is a special parameter that allows for fetching envtemp from the AC
AC_MODE_SPECIAL = "mode"

AC_FAN_SPEED = "ac_mark"


class ACFanSpeed(auto):
    PARAM_NAME = "ac_mark"

    """
    Fan speed levels for AUX air conditioners.
    """
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
HP_HEATER_AUTO_WATER_TEMP_ON = {HP_HEATER_AUTO_WATER_TEMP: 9}
HP_HEATER_AUTO_WATER_TEMP_OFF = {HP_HEATER_AUTO_WATER_TEMP: 0}

HP_WATER_POWER = "hp_pwr"
HP_WATER_POWER_OFF = {HP_WATER_POWER: 0}
HP_WATER_POWER_ON = {HP_WATER_POWER: 1}

HP_QUIET_MODE = "qtmode"

HP_HOT_WATER_TANK_TEMPERATURE = "hp_water_tank_temp"
HP_HOT_WATER_TEMPERATURE_TARGET = "hp_hotwater_temp"

HP_WATER_FAST_HOTWATER = "hp_fast_hotwater"
HP_WATER_FAST_HOTWATER_ON = {HP_WATER_FAST_HOTWATER: 1}
HP_WATER_FAST_HOTWATER_OFF = {HP_WATER_FAST_HOTWATER: 0}


AUX_MODEL_PARAMS_LIST = {
    "000000000000000000000000c3aa0000": [
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
    ],
    "000000000000000000000000c0620000": [
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
        "new_type",
        "ac_tempconvert",
        "sleepdiy",
        "ac_errcode1",
        "tempunit",
        "tenelec",  # Unknown, might be available when the device is in specific state
    ],
}

# Used to fetch params from the device that are not returned in basic call
AUX_MODEL_SPECIAL_PARAMS_LIST = {
    "000000000000000000000000c3aa0000": [HP_HOT_WATER_TANK_TEMPERATURE],
    "000000000000000000000000c0620000": [AC_MODE_SPECIAL],
}


"""
AC PARAMETERS NOT TESTED ALL
'ac_astheat': 0 - Auxiliary heating is off
'ac_clean': 0 - Self-cleaning function is off
'ac_errcode1': 0 - No error code (system functioning normally)
'ac_health': 0 - Health function (likely ionizer/purifier) is off
'ac_mark': 1 - Fan speed 1 is lowest speed (typical speeds: 1=Low, 2=Medium, 3=High, 4=Turbo, 5=Mute)
'ac_mode': 1 - Mode is set to 1, likely "Cool" mode (typical modes: 0=Auto, 1=Cool, 2=Dry, 3=Fan, 4=Heat)
'ac_slp': 0 - Sleep mode is off
'ac_tempconvert': 0 - No temperature conversion happening
'ac_hdir': 0 - Horizontal airflow direction at default/center position
'ac_vdir': 0 - Vertical airflow direction at default/center position
'childlock': 0 - Child lock feature is off
'comfwind': 0 - Comfortable wind mode is off
'ecomode': 0 - Economy/energy-saving mode is off
'envtemp': 236 - Current environment/room temperature (likely 23.6°C)
'err_flag': 0 - No error flag
'mldprf': 0 - Mildew proof/prevention function is off
'model': 1 - Device model identifier
'new_type': 1 - Indicates this is a newer type of AC unit
'pwr': 0 - Power is off (unit is in standby)
'pwrlimit': 0 - Power limitation function is off
'pwrlimitswitch': 0 - Power limit switch is off
'scrdisp': 1 - Screen display is on
'sleepdiy': 1 - Custom sleep mode is on
'temp': 240 - Set temperature (likely 24.0°C)
'tempunit': 1 - Temperature unit (1 typically means Celsius)

HEAT PUMP PARAMETERS NOT TESTED
'hp_pwr'
'hp_water_tank_temp'
'ac_errcode1'
'hp_fast_hotwater'
'err_flag'
'hp_auto_wtemp'
'ac_pwr'
'hp_hotwater_temp'
'ac_temp'
'ac_mode'
'qtmode'
'ecomode'
'ver_old'
"""
