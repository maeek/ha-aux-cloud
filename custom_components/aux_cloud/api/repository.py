"""AUX Cloud family, room, and device repository."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from ..const import DEVICE_QUERY_CONCURRENCY
from ..devices.normalizers import normalize_device_params
from ..devices.profiles import (
    AUX_PROTOCOL_VERSION,
    AUX_QUERY_FAILURES,
    get_product_profile,
    set_protocol_version,
)
from .control import AuxCloudControl
from .errors import AuxApiError, AuxDeviceError, AuxServerError
from .models import AuxDevice
from .protocol.common import build_directive_header
from .session import AuxCloudSession

_LOGGER = logging.getLogger(__name__)
_VERSIONED_QUERY_REQUIRED = -49025


class AuxCloudRepository:
    """Repository for cloud account topology and device bootstrap data."""

    def __init__(self, session: AuxCloudSession, control: AuxCloudControl) -> None:
        """Initialize the repository."""
        self._session = session
        self._control = control
        self._query_semaphore = asyncio.Semaphore(DEVICE_QUERY_CONCURRENCY)
        self._protocol_versions: dict[tuple[str, str], int] = {}

    async def get_families(self) -> list[dict[str, Any]]:
        """List families associated with the user."""
        _LOGGER.debug("Getting families list")
        json_data = await self._session.make_request(
            endpoint="appsync/group/member/getfamilylist",
        )
        _LOGGER.debug("AUX Cloud family query completed")

        data = json_data.get("data")
        families = data.get("familyList") if isinstance(data, dict) else None
        if json_data.get("status") == 0 and isinstance(families, list):
            return cast(list[dict[str, Any]], families)

        raise AuxServerError(
            "Invalid AUX Cloud family response",
            endpoint="appsync/group/member/getfamilylist",
        )

    async def get_devices(
        self,
        familyid: str,
        shared: bool = False,
    ) -> list[AuxDevice]:
        """List devices associated with a family."""
        device_endpoint = (
            "dev/query?action=select"
            if not shared
            else "sharedev/querylist?querytype=shared"
        )
        json_data = await self._session.make_request(
            endpoint=f"appsync/group/{device_endpoint}",
            data_raw='{"pids":[]}' if not shared else '{"endpointId":""}',
            header_overrides={"familyid": familyid},
        )

        if "status" not in json_data or json_data["status"] != 0:
            raise AuxServerError(
                "Invalid AUX Cloud device-list response",
                endpoint=f"appsync/group/{device_endpoint}",
            )

        devices = _extract_devices(json_data)
        state_records = await self._query_device_states(devices)
        online_devices = _initialize_device_snapshots(
            devices,
            familyid=familyid,
            state_records=state_records,
            protocol_versions=self._protocol_versions,
        )
        await asyncio.gather(
            *(self._bootstrap_device(device) for device in online_devices)
        )
        return devices

    async def _bootstrap_device(self, device: AuxDevice) -> None:
        """Fetch, merge, and normalize one online device snapshot."""
        profile = get_product_profile(device.get("productId"))
        queries = profile.initial_param_queries(device)
        results = await asyncio.gather(
            *(self._bounded_get_device_params(device, query) for query in queries),
            return_exceptions=True,
        )
        merged_params, query_failures = _merge_param_results(queries, results)
        fallback_params, fallback_failures = await self._fetch_fallback_params(
            device,
            profile.fallback_param_queries(device),
            results,
        )
        merged_params.update(fallback_params)
        query_failures.extend(fallback_failures)
        self._store_initial_params(device, merged_params, query_failures)

    async def _fetch_fallback_params(
        self,
        device: AuxDevice,
        fallback_queries: list[list[str]],
        initial_results: list[dict[str, Any] | BaseException],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Retry a legacy heat-pump bootstrap when the device requires v3."""
        if not (
            fallback_queries
            and any(
                isinstance(result, AuxApiError)
                and result.code == _VERSIONED_QUERY_REQUIRED
                for result in initial_results
            )
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
        return _merge_param_results(fallback_queries, fallback_results)

    def _store_initial_params(
        self,
        device: AuxDevice,
        params: dict[str, Any],
        query_failures: list[dict[str, Any]],
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
        cache_key = _protocol_cache_key(device)
        if cache_key and (protocol_version := device.get(AUX_PROTOCOL_VERSION)):
            self._protocol_versions[cache_key] = protocol_version
        normalize_device_params(device)

    async def _bounded_get_device_params(
        self, device: AuxDevice, params: list[str]
    ) -> dict[str, Any]:
        """Query one parameter set without exceeding cloud concurrency limits."""
        async with self._query_semaphore:
            return await self._control.get_device_params(device, params=params)

    async def _query_device_states(
        self, devices: list[AuxDevice]
    ) -> list[dict[str, Any]]:
        """Query state for a list of devices."""
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
                ),
                "payload": {"studata": queried_devices, "msgtype": "batch"},
            }
        }

        json_data = await self._session.make_request(
            endpoint="device/control/v2/querystate",
            data=data,
        )

        event = json_data.get("event")
        payload = event.get("payload") if isinstance(event, dict) else None
        if (
            isinstance(payload, dict)
            and payload.get("status") == 0
            and isinstance(payload.get("data"), list)
        ):
            return cast(list[dict[str, Any]], payload["data"])

        raise AuxServerError(
            "Invalid AUX Cloud device-state response",
            endpoint="device/control/v2/querystate",
        )


def _extract_devices(json_data: dict[str, Any]) -> list[AuxDevice]:
    """Extract personal or shared device records from a device-list response."""
    data = json_data.get("data")
    if not isinstance(data, dict):
        return []
    if isinstance(data.get("endpoints"), list):
        return cast(list[AuxDevice], data["endpoints"])
    if isinstance(data.get("shareFromOther"), list):
        return [
            cast(AuxDevice, dev["devinfo"])
            for dev in data["shareFromOther"]
            if isinstance(dev, dict) and isinstance(dev.get("devinfo"), dict)
        ]
    return []


def _initialize_device_snapshots(
    devices: list[AuxDevice],
    *,
    familyid: str,
    state_records: list[dict[str, Any]],
    protocol_versions: dict[tuple[str, str], int],
) -> list[AuxDevice]:
    """Attach family, availability, params, and cached protocol metadata."""
    states_by_endpoint = {
        state["did"]: state.get("state", 0)
        for state in state_records
        if isinstance(state, dict) and isinstance(state.get("did"), str)
    }
    online_devices: list[AuxDevice] = []
    for device in devices:
        device.setdefault("familyId", familyid)
        endpoint_id = device.get("endpointId")
        cache_key = _protocol_cache_key(device)
        if cache_key and cache_key in protocol_versions:
            device[AUX_PROTOCOL_VERSION] = protocol_versions[cache_key]
        state = states_by_endpoint.get(endpoint_id, 0)
        device["state"] = state if isinstance(state, int) else 0
        device["params"] = {}
        if device["state"] == 1:
            online_devices.append(device)
    return online_devices


def _protocol_cache_key(device: AuxDevice) -> tuple[str, str] | None:
    """Return an endpoint/product key safe from device-replacement reuse."""
    endpoint_id = device.get("endpointId")
    product_id = device.get("productId")
    if endpoint_id and product_id:
        return endpoint_id, product_id
    return None


def _merge_param_results(
    queries: list[list[str]],
    query_results: list[dict[str, Any] | BaseException],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Merge successful query batches and describe individual failures."""
    merged_params: dict[str, Any] = {}
    query_failures: list[dict[str, Any]] = []
    for query, params in zip(queries, query_results, strict=True):
        if isinstance(params, BaseException):
            _log_param_query_error(query, params)
            query_failures.append(_query_failure(query, params))
            continue
        if params:
            merged_params.update(params)
    return merged_params, query_failures


def _log_param_query_error(
    query: list[str],
    error: BaseException,
) -> None:
    """Log bootstrap parameter query errors at an appropriate severity."""
    log_message = "Error fetching AUX device params %s (%s)"
    log_args = (query, type(error).__name__)
    if isinstance(error, AuxDeviceError):
        _LOGGER.debug(log_message, *log_args)
        return
    _LOGGER.error(log_message, *log_args)


def _query_failure(query: list[str], error: BaseException) -> dict[str, Any]:
    """Return a sanitized query failure for downloadable diagnostics."""
    return {
        "params": list(query),
        "error_type": type(error).__name__,
        "code": getattr(error, "code", None),
    }
