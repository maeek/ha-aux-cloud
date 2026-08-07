"""Live test against a real AUX Cloud account/device.

Mimics exactly what the Home Assistant integration does when you change the
target temperature:

  1. Optimistically apply the new value locally (DeviceStateHelper.apply_optimistic)
  2. Send the "set" command to AUX Cloud (AuxCloudAPI.set_device_params)
  3. Immediately poll fresh params from the cloud (AuxCloudAPI.get_device_params),
     exactly like coordinator.async_request_refresh() would trigger
  4. Feed that poll into DeviceStateHelper.process_new_payload() and check
     whether the optimistic value survived the (possibly stale) poll.

Not committed to git - reads credentials from docs/dev/config.yaml (gitignored).
"""

import asyncio
import os
import pathlib
import pprint
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
    print(f"Logging in (region={region})...")
    await cloud.login(email, password)

    families = await cloud.get_families()
    if not families:
        print("No families found on this account.")
        return

    all_devices = []
    for family in families:
        devices = await cloud.get_devices(family["familyid"], shared=shared)
        all_devices.extend(devices or [])

    if not all_devices:
        print("No devices found.")
        return

    print(f"\nFound {len(all_devices)} device(s):")
    for i, dev in enumerate(all_devices):
        print(f"  [{i}] {dev.get('friendlyName')} ({dev.get('endpointId')})")

    device = all_devices[0]
    print(f"\nUsing device: {device.get('friendlyName')}")

    current_params = device.get("params", {})
    print("\nCurrent params:")
    pprint.pprint(current_params)

    current_temp = current_params.get(AC_TEMPERATURE_TARGET)
    if current_temp is None:
        print(f"\nDevice has no '{AC_TEMPERATURE_TARGET}' param, cannot test.")
        return

    current_temp_c = current_temp / 10
    # Bump target temp by 1C (wrap if it would go out of a sane AC range).
    new_temp_c = current_temp_c + 1 if current_temp_c < 30 else current_temp_c - 1
    new_temp = int(new_temp_c * 10)

    print(f"\nCurrent target temp: {current_temp_c}C")
    print(f"Will set target temp: {new_temp_c}C")

    # --- Mirror exactly what BaseEntity._set_device_params() does ---
    helper = DeviceStateHelper(current_params, max_failed_polls=5)

    print("\n[1] Applying optimistic update locally...")
    helper.apply_optimistic({AC_TEMPERATURE_TARGET: new_temp})
    print(f"    Local cached target temp is now: {helper.current_params[AC_TEMPERATURE_TARGET] / 10}C")

    print("\n[2] Sending 'set' command to AUX Cloud...")
    await cloud.set_device_params(device, {AC_TEMPERATURE_TARGET: new_temp})
    print("    Set command sent.")

    print("\n[3] Immediately polling fresh params from the cloud (like async_request_refresh)...")
    fresh_params = await cloud.get_device_params(device, params=[])
    print(f"    Cloud reported target temp: {fresh_params.get(AC_TEMPERATURE_TARGET, 'N/A')}")

    print("\n[4] Feeding poll result into DeviceStateHelper.process_new_payload()...")
    helper.process_new_payload(fresh_params, device.get("friendlyName", "AC"), update_id=1)
    result_temp = helper.current_params.get(AC_TEMPERATURE_TARGET)
    print(f"    Local cached target temp after poll: {result_temp / 10 if result_temp is not None else 'N/A'}C")

    if result_temp == new_temp:
        print("\n>>> PASS: Optimistic value held (either confirmed or protected from stale echo).")
    else:
        print(f"\n>>> FAIL: Value reverted to {result_temp / 10}C instead of staying at {new_temp_c}C!")

    # Give the real device a few seconds, then poll again to see convergence.
    print("\nWaiting 5s then polling again to check real device convergence...")
    await asyncio.sleep(5)
    fresh_params_2 = await cloud.get_device_params(device, params=[])
    print(f"Cloud reported target temp after 5s: {fresh_params_2.get(AC_TEMPERATURE_TARGET, 'N/A')}")
    helper.process_new_payload(fresh_params_2, device.get("friendlyName", "AC"), update_id=2)
    result_temp_2 = helper.current_params.get(AC_TEMPERATURE_TARGET)
    print(f"Local cached target temp after 2nd poll: {result_temp_2 / 10 if result_temp_2 is not None else 'N/A'}C")


if __name__ == "__main__":
    asyncio.run(main())
