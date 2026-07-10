"""AUX Cloud family, room, and device repository."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from ..const import DEVICE_QUERY_CONCURRENCY
from ..devices.normalizers import normalize_device_params
from ..devices.profiles import (
    AUX_PROTOCOL_VERSION,
    AUX_QUERY_FAILURES,
    fallback_param_queries,
    initial_param_queries,
    set_protocol_version,
)
from .control import AuxCloudControlService
from .errors import AuxApiError, AuxDeviceError, AuxServerError
from .protocol.common import build_directive_header
from .session import AuxCloudSession

_LOGGER = logging.getLogger(__name__)
_VERSIONED_QUERY_REQUIRED = -49025


@dataclass(slots=True)
class _InitialParamQueryPlan:
    """Parameter queries required to bootstrap one online device."""

    device: dict
    queries: list[list[str]]


class AuxCloudRepository:
    """Repository for cloud account topology and device bootstrap data."""

    def __init__(
        self, session: AuxCloudSession, control: AuxCloudControlService
    ) -> None:
        """Initialize the repository."""
        self._session = session
        self._control = control
        self.families: dict | None = None
        self._query_semaphore = asyncio.Semaphore(DEVICE_QUERY_CONCURRENCY)
        self._protocol_versions: dict[str, int] = {}

    async def get_families(self):
        """List families associated with the user."""
        _LOGGER.debug("Getting families list")
        json_data = await self._session.make_request(
            method="POST",
            endpoint="appsync/group/member/getfamilylist",
            headers=self._session.get_headers(),
        )
        _LOGGER.debug("AUX Cloud family query completed")

        if "status" in json_data and json_data["status"] == 0:
            families = {}
            for family in json_data["data"]["familyList"]:
                families[family["familyid"]] = {
                    "id": family["familyid"],
                    "name": family["name"],
                    "rooms": [],
                    "devices": [],
                }
            self.families = families
            return json_data["data"]["familyList"]

        raise AuxServerError(
            "Invalid AUX Cloud family response",
            endpoint="appsync/group/member/getfamilylist",
        )

    async def get_rooms(self, familyid: str):
        """List rooms associated with a family."""
        _LOGGER.debug("Getting AUX Cloud rooms")
        json_data = await self._session.make_request(
            method="POST",
            endpoint="appsync/group/room/query",
            headers=self._session.get_headers(familyid=familyid),
        )

        if "status" in json_data and json_data["status"] == 0:
            if self.families is None:
                self.families = {}
            for room in json_data["data"]["roomList"]:
                self.families[room["familyid"]]["rooms"].append(
                    {"id": room["roomid"], "name": room["name"]}
                )

            return json_data["data"]["roomList"]

        raise AuxServerError(
            "Invalid AUX Cloud room response",
            endpoint="appsync/group/room/query",
        )

    async def get_devices(
        self,
        familyid: str,
        shared=False,
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
        )

        if "status" not in json_data or json_data["status"] != 0:
            raise AuxServerError(
                "Invalid AUX Cloud device-list response",
                endpoint=f"appsync/group/{device_endpoint}",
            )

        devices = _extract_devices(json_data)
        for dev in devices:
            dev.setdefault("familyId", familyid)

        device_states = await self.bulk_query_device_state(devices)
        await self._fetch_initial_params(devices, device_states)
        return devices

    async def _fetch_initial_params(
        self, devices: list[dict], device_states: dict
    ) -> None:
        """Fetch initial parameter snapshots for discovered devices."""
        query_plans = self._prepare_initial_param_queries(devices, device_states)
        if not query_plans:
            return

        results = await asyncio.gather(
            *(
                asyncio.gather(
                    *(
                        self._bounded_get_device_params(plan.device, query)
                        for query in plan.queries
                    ),
                    return_exceptions=True,
                )
                for plan in query_plans
            ),
            return_exceptions=True,
        )

        for plan, query_results in zip(query_plans, results, strict=True):
            await self._apply_initial_param_results(plan, query_results)

    def _prepare_initial_param_queries(
        self, devices: list[dict], device_states: dict
    ) -> list[_InitialParamQueryPlan]:
        """Initialize device state and plan queries for online devices."""
        states_by_endpoint = {
            state["did"]: state["state"] for state in device_states["data"]
        }
        query_plans = []
        for device in devices:
            endpoint_id = device.get("endpointId")
            if endpoint_id in self._protocol_versions:
                device[AUX_PROTOCOL_VERSION] = self._protocol_versions[endpoint_id]
            device["state"] = states_by_endpoint.get(endpoint_id, 0)
            device["params"] = {}

            is_online = device["state"] == 1
            _LOGGER.debug("AUX device is %s", "online" if is_online else "offline")
            if not is_online:
                _LOGGER.debug(
                    "Skipping initial parameter query for an offline AUX device"
                )
                continue
            query_plans.append(
                _InitialParamQueryPlan(device, initial_param_queries(device))
            )
        return query_plans

    async def _apply_initial_param_results(
        self,
        plan: _InitialParamQueryPlan,
        query_results: list[dict | BaseException | None] | BaseException,
    ) -> None:
        """Merge one device's query results and persist its snapshot."""
        if isinstance(query_results, BaseException) or not query_results:
            _LOGGER.error(
                "AUX device bootstrap failed (%s)",
                type(query_results).__name__,
            )
            return

        merged_params, query_failures = _merge_initial_param_results(
            plan, query_results
        )
        fallback_params, fallback_failures = await self._fetch_fallback_params(
            plan.device, query_results[0]
        )
        merged_params.update(fallback_params)
        query_failures.extend(fallback_failures)
        self._store_initial_params(plan.device, merged_params, query_failures)

    async def _fetch_fallback_params(
        self, device: dict, primary_result: dict | BaseException | None
    ) -> tuple[dict, list[dict]]:
        """Retry heat-pump bootstrap with versioned queries when required."""
        fallback_queries = fallback_param_queries(device)
        if not (
            fallback_queries
            and isinstance(primary_result, AuxApiError)
            and primary_result.code == _VERSIONED_QUERY_REQUIRED
        ):
            return {}, []

        _LOGGER.debug("Retrying AUX heat-pump bootstrap with versioned queries")
        fallback_results = await asyncio.gather(
            *(
                self._bounded_get_device_params(device, query)
                for query in fallback_queries
            ),
            return_exceptions=True,
        )
        merged_params = {}
        query_failures = []
        for query, params in zip(fallback_queries, fallback_results, strict=True):
            if isinstance(params, BaseException):
                query_failures.append(_query_failure(query, params))
            elif params:
                merged_params.update(params)
        return merged_params, query_failures

    def _store_initial_params(
        self, device: dict, params: dict, query_failures: list[dict]
    ) -> None:
        """Store a normalized initial snapshot and its diagnostics."""
        device["params"] = params
        if query_failures:
            device[AUX_QUERY_FAILURES] = query_failures
        else:
            device.pop(AUX_QUERY_FAILURES, None)
        if not params:
            return

        set_protocol_version(device, params.get("ver"))
        if protocol_version := device.get(AUX_PROTOCOL_VERSION):
            self._protocol_versions[device["endpointId"]] = protocol_version
        normalize_device_params(device)
        device["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    async def _bounded_get_device_params(
        self, device: dict, params: list[str]
    ) -> dict | None:
        """Query one parameter set without exceeding cloud concurrency limits."""
        async with self._query_semaphore:
            return await self._control.get_device_params(device, params=params)

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
                    message_id_prefix=self._session.userid or "",
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
        )

        if (
            "event" in json_data
            and "payload" in json_data["event"]
            and json_data["event"]["payload"]["status"] == 0
        ):
            return json_data["event"]["payload"]

        raise AuxServerError(
            "Invalid AUX Cloud device-state response",
            endpoint="device/control/v2/querystate",
        )

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
                    message_id_prefix=self._session.userid or "",
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
        )

        if (
            "event" in json_data
            and "payload" in json_data["event"]
            and json_data["event"]["payload"]["status"] == 0
        ):
            return json_data["event"]["payload"]

        raise AuxServerError(
            "Invalid AUX Cloud device-state response",
            endpoint="device/control/v2/querystate",
        )


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


def _merge_initial_param_results(
    plan: _InitialParamQueryPlan,
    query_results: list[dict | BaseException | None],
) -> tuple[dict, list[dict]]:
    """Merge successful initial queries and describe individual failures."""
    merged_params = {}
    query_failures = []
    for query_index, (query, params) in enumerate(
        zip(plan.queries, query_results, strict=True)
    ):
        if isinstance(params, BaseException):
            _log_param_query_error(query_index, params)
            query_failures.append(_query_failure(query, params))
            continue
        if params is None:
            _LOGGER.error(
                "Empty %s AUX device parameter response",
                _param_query_label(query_index),
            )
            continue
        if params:
            merged_params.update(params)
    return merged_params, query_failures


def _log_param_query_error(
    query_index: int,
    error: BaseException,
) -> None:
    """Log bootstrap parameter query errors at an appropriate severity."""
    log_message = "Error fetching %s AUX device params (%s)"
    log_args = (_param_query_label(query_index), type(error).__name__)
    if isinstance(error, AuxDeviceError):
        _LOGGER.debug(log_message, *log_args)
        return
    _LOGGER.error(log_message, *log_args)


def _query_failure(query: list[str], error: BaseException) -> dict:
    """Return a sanitized query failure for downloadable diagnostics."""
    return {
        "params": list(query),
        "error_type": type(error).__name__,
        "code": getattr(error, "code", None),
    }
