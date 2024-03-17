import pprint
import asyncio

from aux_cloud import AuxCloudAPI

if __name__ == "__main__":
  # Example usage
  async def main():
    cloud = AuxCloudAPI()
    email = ''
    password = ''
    # print(
    await cloud.login(email, password)
    # )
    print('')
    # print('Family data:')
    family_data = await cloud.list_families()
    # print(family_data)
    # print('')

    for family in family_data['familyList']:
      # room_data = await cloud.list_rooms(family['familyid'])
      # print('Room data:')
      # print(room_data)
      # print('')
      # print('Device data:')
      # dev_data = await cloud.list_devices(family['familyid'])
      # print(dev_data)
      # print('')
      # print('Shared device data:')
      dev_data = await cloud.list_devices(family['familyid'], True)
      # print(dev_data)
      print('')

      # for dev in dev_data:
      print('Device state:')
      pprint.pprint(await cloud.query_device_state(
          dev_data[1]['endpointId'],
          dev_data[1]['devSession']
      ))
      print('')

      print('Device params:')
      pprint.pprint(await cloud.get_device_params(
          dev_data[0],
          [
              # 'hp_water_tank_temp', # For some reason this needs to be queried separately
              # Other values are returned by default
              # 'ver_old',
              # 'ac_mode',
              # 'ac_pwr',
              # 'ac_temp',
              # 'ecomode',
              # 'hp_auto_wtemp',
              # 'hp_fast_hotwater',
              # 'hp_hotwater_temp',
              # 'hp_pwr',
              # 'qtmode'
          ]
      ))
      print('')

    # device_data = await cloud.query_device_state('', 25280, '')
    # print('Device state:')
    # print(device_data)

  loop = asyncio.get_event_loop()
  loop.run_until_complete(main())
