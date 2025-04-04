from enum import auto

# Used to fetch params from the device that are not returned in basic call
AUX_MODEL_TO_PARAMS = {
    "000000000000000000000000c0620000": ["mode"],
    "000000000000000000000000c3aa0000": ["hp_water_tank_temp"],
}

AUX_MODEL_TO_NAME = {
    "000000000000000000000000c3aa0000": "AUX Heat Pump",
    "000000000000000000000000c0620000": "AUX Air Conditioner",
}

AC = "Air Conditioner"
HEAT_PUMP = "Heat Pump"


class AUX_PRODUCT_CATEGORY(auto):
    HEAT_PUMP = ["000000000000000000000000c3aa0000"]

    AC = ["000000000000000000000000c0620000"]


# Common constants
AUX_MODE = "ac_mode"
AUX_MODE_AUTO = {AUX_MODE: 0}
AUX_MODE_COOLING = {AUX_MODE: 1}
AUX_MODE_DRY = {AUX_MODE: 2}
AUX_MODE_FAN = {AUX_MODE: 3}
AUX_MODE_HEATING = {AUX_MODE: 4}

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

AC_SWING_VERTICAL = "ac_vdir"
AC_SWING_VERTICAL_ON = {AC_SWING_VERTICAL: 1}
AC_SWING_VERTICAL_OFF = {AC_SWING_VERTICAL: 0}

AC_SWING_HORIZONTAL = "ac_hdir"
AC_SWING_HORIZONTAL_ON = {AC_SWING_HORIZONTAL: 1}
AC_SWING_HORIZONTAL_OFF = {AC_SWING_HORIZONTAL: 0}


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


# -----
FAN_SPEEDS_LOW = {"ac_mark": 1}
FAN_SPEEDS_HIGH: dict = {"ac_mark": 4}

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
