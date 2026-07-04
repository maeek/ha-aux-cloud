"""AUX Cloud family, room, and device repository."""

from __future__ import annotations

import asyncio
import logging
import time

from ..devices.normalizers import normalize_device_params
from ..devices.profiles import initial_param_queries
from .control import AuxCloudControlService
from .errors import AuxDeviceError
from .protocol.common import build_directive_header
from .session import AuxCloudSession

_LOGGER = logging.getLogger(__name__)


class AuxCloudRepository:
    """Repository for cloud account topology and device bootstrap data."""

    def __init__(
        self, session: AuxCloudSession, control: AuxCloudControlService
    ) -> None:
        """Initialize the repository."""
        self._session = session
        self._control = control
        self.families: dict | None = None

    async def get_families(self):
        """List families associated with the user."""
        _LOGGER.debug("Getting families list")
        json_data = await self._session.make_request(
            method="POST",
            endpoint="appsync/group/member/getfamilylist",
            headers=self._session.get_headers(),
            ssl=False,
        )
        _LOGGER.debug("Families response: %s", json_data)

        if self.families is None:
            self.families = {}

        if "status" in json_data and json_data["status"] == 0:
            for family in json_data["data"]["familyList"]:
                self.families[family["familyid"]] = {
                    "id": family["familyid"],
                    "name": family["name"],
                    "rooms": [],
                    "devices": [],
                }
            return json_data["data"]["familyList"]

        raise ValueError(f"Failed to get families list: {json_data}")

    async def get_rooms(self, familyid: str):
        """List rooms associated with a family."""
        _LOGGER.debug("Getting rooms list for family %s", familyid)
        json_data = await self._session.make_request(
            method="POST",
            endpoint="appsync/group/room/query",
            headers=self._session.get_headers(familyid=familyid),
            ssl=False,
        )

        if "status" in json_data and json_data["status"] == 0:
            for room in json_data["data"]["roomList"]:
                self.families[room["familyid"]]["rooms"].append(
                    {"id": room["roomid"], "name": room["name"]}
                )

            return json_data["data"]["roomList"]

        raise ValueError(f"Failed to query a room: {json_data}")

    async def get_devices(
        self,
        familyid: str,
        shared=False,
        selected_devices: list[str] = None,
    ):
        """List devices associated with a family."""
        device_endpoint = (
            "dev/query?action=select"
            if not shared
            else "sharedev/querylist?querytype=shared"
        )
        json_data = await self._session.make_request(
            method="POST",
            endpoint=f"appsync/group/{device_endpoint}",
            data_raw='{"pids":[]}' if not shared else '{"endpointId":""}',
            headers=self._session.get_headers(familyid=familyid),
            ssl=False,
        )

        if "status" not in json_data or json_data["status"] != 0:
            raise ValueError(f"Failed to query devices: {json_data}")

        devices = _extract_devices(json_data)
        if selected_devices is not None:
            devices = [dev for dev in devices if dev["endpointId"] in selected_devices]

        for dev in devices:
            dev.setdefault("familyId", familyid)

        device_states = await self.bulk_query_device_state(devices)
        await self._fetch_initial_params(devices, device_states)
        return devices

    async def _fetch_initial_params(
        self, devices: list[dict], device_states: dict
    ) -> None:
        """Fetch initial parameter snapshots for discovered devices."""
        param_tasks = []

        for dev in devices:
            dev["state"] = next(
                (
                    dev_state["state"]
                    for dev_state in device_states["data"]
                    if dev_state["did"] == dev["endpointId"]
                ),
                0,
            )
            dev["params"] = {}

            _LOGGER.debug(
                "Device %s is %s - %s",
                dev["endpointId"],
                "online" if dev["state"] == 1 else "offline",
                dev,
            )
            if dev["state"] != 1:
                _LOGGER.debug(
                    "Skipping initial parameter query for offline AUX device %s",
                    dev["endpointId"],
                )
                continue

            query_tasks = [
                asyncio.create_task(self._control.get_device_params(dev, params=query))
                for query in initial_param_queries(dev)
            ]
            param_tasks.append((dev, query_tasks))

        if not param_tasks:
            return

        results = await asyncio.gather(
            *[
                asyncio.gather(*query_tasks, return_exceptions=True)
                for _, query_tasks in param_tasks
            ],
            return_exceptions=True,
        )

        for index, (dev, _) in enumerate(param_tasks):
            query_results = results[index]
            if isinstance(query_results, BaseException) or not query_results:
                _LOGGER.error(
                    "Error fetching device params for %s: %s",
                    dev["endpointId"],
                    query_results,
                )
                continue

            merged_params = {}
            for query_index, params in enumerate(query_results):
                if isinstance(params, BaseException):
                    _log_param_query_error(dev, query_index, params)
                    continue
                if params is None:
                    _LOGGER.error(
                        "Error fetching %s device params for %s: empty response",
                        _param_query_label(query_index),
                        dev["endpointId"],
                    )
                    continue
                if params:
                    merged_params.update(params)

            dev["params"] = merged_params
            if not merged_params:
                continue

            normalize_device_params(dev)
            dev["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    async def query_device_state(self, device_id: str, dev_session: str):
        """Query one device state."""
        timestamp = int(time.time())
        queried_device = [{"did": device_id, "devSession": dev_session}]
        data = {
            "directive": {
                "header": build_directive_header(
                    namespace="DNA.QueryState",
                    name="queryState",
                    messageType="controlgw.batch",
                    message_id_prefix=self._session.userid,
                    timstamp=f"{timestamp}",
                ),
                "payload": {"studata": queried_device, "msgtype": "batch"},
            }
        }

        json_data = await self._session.make_request(
            method="POST",
            endpoint="device/control/v2/querystate",
            data=data,
            headers=self._session.get_headers(),
            ssl=False,
        )

        if (
            "event" in json_data
            and "payload" in json_data["event"]
            and json_data["event"]["payload"]["status"] == 0
        ):
            return json_data["event"]["payload"]

        raise ValueError(f"Failed to query device state: {json_data}")

    async def bulk_query_device_state(self, devices: list[dict]):
        """Query state for a list of devices."""
        timestamp = int(time.time())
        queried_devices = [
            {"did": dev["endpointId"], "devSession": dev["devSession"]}
            for dev in devices
        ]
        data = {
            "directive": {
                "header": build_directive_header(
                    namespace="DNA.QueryState",
                    name="queryState",
                    messageType="controlgw.batch",
                    message_id_prefix=self._session.userid,
                    timstamp=f"{timestamp}",
                ),
                "payload": {"studata": queried_devices, "msgtype": "batch"},
            }
        }

        json_data = await self._session.make_request(
            method="POST",
            endpoint="device/control/v2/querystate",
            data=data,
            headers=self._session.get_headers(),
            ssl=False,
        )

        if (
            "event" in json_data
            and "payload" in json_data["event"]
            and json_data["event"]["payload"]["status"] == 0
        ):
            return json_data["event"]["payload"]

        raise ValueError(f"Failed to query device state: {json_data}")


def _extract_devices(json_data: dict) -> list[dict]:
    """Extract personal or shared device records from a device-list response."""
    if "endpoints" in json_data["data"]:
        return json_data["data"]["endpoints"] or []
    if "shareFromOther" in json_data["data"]:
        return [dev["devinfo"] for dev in json_data["data"]["shareFromOther"]]
    return []


def _param_query_label(query_index: int) -> str:
    """Return a human-readable bootstrap parameter query label."""
    return "primary" if query_index == 0 else "special"


def _log_param_query_error(
    device: dict,
    query_index: int,
    error: BaseException,
) -> None:
    """Log bootstrap parameter query errors at an appropriate severity."""
    log_message = "Error fetching %s device params for %s: %s"
    log_args = (_param_query_label(query_index), device["endpointId"], error)
    if isinstance(error, AuxDeviceError):
        _LOGGER.debug(log_message, *log_args)
        return
    _LOGGER.error(log_message, *log_args)
