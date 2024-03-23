
# TODO: Update params
AUX_MODELS = {
    "000000000000000000000000c3aa0000": {
      "type": "heat_pump",
      "params": {
        'ver_old': {
          'name': 'ver_old',
          'ajustable': False
        },
        'ac_mode': {
          'name': 'ac_mode',
          'ajustable': True,
          'values': {}
        },
        'ac_pwr': {
          'name': 'ac_pwr',
          'ajustable': True,
          'values': {
            '0': 'off',
            '1': 'on'
          }
        },
        'ac_temp': {
          'name': 'ac_temp',
          'ajustable': True,
          'values': {},
          'min': 0,
          'max': 64
        },
        'ecomode': {
          'name': 'ecomode',
          'ajustable': True,
          'values': {
            '0': 'off',
            '1': 'on'
          }
        },
        'hp_auto_wtemp': {
          'name': 'hp_auto_wtemp',
          'ajustable': True,
          'values': {},
          'min': 0,
          'max': 64
        },
        'hp_fast_hotwater': {
          'name': 'hp_fast_hotwater',
          'ajustable': True,
          'values': {
            '0': 'off',
            '1': 'on'
          }
        },
        'hp_hotwater_temp': {
          'name': 'hp_hotwater_temp',
          'ajustable': True,
          'values': {},
          'min': 0,
          'max': 64
        },
        'hp_pwr': {
          'name': 'hp_pwr',
          'ajustable': True,
          'values': {
            '0': 'off',
            '1': 'on'
          }
        },
        'qtmode': {
          'name': 'qtmode',
          'ajustable': True,
          'values': {
            '0': 'off',
            '1': 'on'
          }
        },
      },
      "special_params": {
        'hp_water_tank_temp': {
          'name': 'hp_water_tank_temp',
          'ajustable': False
        },
      }
    },
    "000000000000000000000000c0620000": {
      "type": "air_conditioner",
      "params": {},
      "special_params": {}
    },
}

AUX_MODEL_TO_NAME = {
  "000000000000000000000000c3aa0000": "AUX Heat Pump",
  "000000000000000000000000c0620000": "AUX Air Conditioner",
}
