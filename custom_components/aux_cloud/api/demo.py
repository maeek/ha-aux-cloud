import asyncio
import os
import pathlib
import pprint

import yaml

from aux_cloud import AuxCloudAPI


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

        families = await cloud.get_families()
        for family in families:
            print("FamilyId {family['familyid']}:")
            devices = await cloud.get_devices(family['familyid'], shared)
            if devices:
                print("Devices:")
                pprint.pprint(devices)
                for device in devices:
                    state = await cloud.query_device_state(
                        device['endpointId'],
                        device['devSession'])

                    print("Device state:")
                    pprint.pprint(state)
                    print("devSession {device['devSession']}")
                    params = await cloud.get_device_params(device)
                    print("Device params:")
                    pprint.pprint(params)
                    # await cloud.set_device_params(device, POWER_OFF)
                    # await cloud.set_device_params(device, HEATING)
                    # await cloud.set_device_params(device, TEMP)
                    # await cloud.set_device_params(device, FAN_SPEEDS_HIGH)

                    params = await cloud.get_device_params(device)

                    print("Device params after set:")
                    pprint.pprint(params)

                print("")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
