"""Rapid-fire live test: set -> poll immediately (no sleep) in a tight loop to
try to catch the AUX cloud returning a stale/pre-command value, and confirm the
DeviceStateHelper's optimistic protection holds the correct value regardless.

Not committed to git - reads credentials from docs/dev/config.yaml (gitignored).
"""

import asyncio
import os
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

from custom_components.aux_cloud.api.aux_cloud import AuxCloudAPI
from custom_components.aux_cloud.api.const import AC_TEMPERATURE_TARGET
from custom_components.aux_cloud.util import DeviceStateHelper


def get_config_path():
    current_dir = pathlib.Path(__file__).parent
    return os.path.join(current_dir, "config.yaml")


async def main():
    with open(get_config_path(), "r", encoding="utf-8") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    email = config["email"]
    password = config["password"]
    shared = config.get("shared", False)
    region = config.get("region", "eu")

    cloud = AuxCloudAPI(region=region)
    await cloud.login(email, password)

    families = await cloud.get_families()
    all_devices = []
    for family in families:
        devices = await cloud.get_devices(family["familyid"], shared=shared)
        all_devices.extend(devices or [])

    device = all_devices[0]
    print(f"Using device: {device.get('friendlyName')}")

    current_temp = device["params"][AC_TEMPERATURE_TARGET]
    helper = DeviceStateHelper(device["params"], max_failed_polls=5)

    temps_c = [23.0, 24.0, 22.0, 25.0, 23.0]
    stale_hits = 0

    for temp_c in temps_c:
        new_temp = int(temp_c * 10)
        print(f"\nSetting target temp -> {temp_c}C")
        helper.apply_optimistic({AC_TEMPERATURE_TARGET: new_temp})

        await cloud.set_device_params(device, {AC_TEMPERATURE_TARGET: new_temp})

        # Immediately poll with no delay at all - worst case race.
        fresh_params = await cloud.get_device_params(device, params=[])
        raw_cloud_val = fresh_params.get(AC_TEMPERATURE_TARGET)
        print(f"  Raw cloud value immediately after set: {raw_cloud_val / 10 if raw_cloud_val is not None else 'N/A'}C")

        if raw_cloud_val != new_temp:
            stale_hits += 1
            print("  -> STALE ECHO DETECTED from cloud (this is exactly what used to cause the revert bug)")

        helper.process_new_payload(fresh_params, device.get("friendlyName", "AC"), update_id=id(fresh_params))
        result = helper.current_params.get(AC_TEMPERATURE_TARGET)
        held = result == new_temp
        print(f"  Helper's cached value after feeding poll: {result / 10}C -> {'HELD correctly' if held else 'REVERTED (BUG)'}")

        if not held:
            print("  !!! FIX FAILED TO PROTECT VALUE !!!")

    print(f"\nStale cloud echoes observed: {stale_hits}/{len(temps_c)}")
    print("Restoring original temp...")
    await cloud.set_device_params(device, {AC_TEMPERATURE_TARGET: current_temp})


if __name__ == "__main__":
    asyncio.run(main())
