import pprint
import asyncio
import yaml

from aux_cloud import AuxCloudAPI
import os
import pathlib


def get_config_path():
  current_dir = pathlib.Path(__file__).parent
  custom_components_dir = current_dir.parent.parent
  return os.path.join(custom_components_dir, 'dev', 'config.yaml')

if __name__ == "__main__":

  with open(get_config_path(), "r", encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.FullLoader)
  email: str = config['email']
  password: str = config['password']
  shared: bool = config['shared']

  # Example usage
  async def main():
    cloud = AuxCloudAPI()
    await cloud.login(email, password)

    families = await cloud.list_families()
    for family in families:
      print(f"FamilyId {family['familyid']}:")
      devices = await cloud.list_devices(family['familyid'], shared)
      if devices:
        print(f"Devices:")
        pprint.pprint(devices)
        for device in devices:

          state = await cloud.query_device_state(
            device['endpointId'],
            device['devSession']
          )
          print("Device state:")
          pprint.pprint(state)
          print(f"devSession {device['devSession']}")
          params = await cloud.get_device_params(device)
          print(f"Device params:")
          pprint.pprint(params)
          param: dict = {"pwr": 0}
          await cloud.set_device_params(device, param)
          param: dict = {"temp": 250}
          await cloud.set_device_params(device, param)
          params = await cloud.get_device_params(device)

          print(f"Device params after set:")
          pprint.pprint(params)

        print("")



  # Cleaned up by standardizing variable names, removing debugging statements,
  # improving readability, and more.

  loop = asyncio.get_event_loop()
  loop.run_until_complete(main())
