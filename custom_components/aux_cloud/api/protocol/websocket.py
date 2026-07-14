"""WebSocket protocol parsing for AUX Cloud."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..errors import SUCCESS_STATUSES, AuxServerError, raise_for_cloud_response
from ..models import AuxDevice, DeviceUpdate
from .common import decode_json_payload, parse_std_data


def build_device_subscriptions(devices: Iterable[AuxDevice]) -> list[dict[str, Any]]:
    """Build relay subscription records for an account snapshot."""
    return [
        {
            "devSession": device.get("devSession", ""),
            "endpointId": endpoint_id,
            "gatewayId": device.get("gatewayId", ""),
            "pid": device.get("productId", ""),
        }
        for device in devices
        if (endpoint_id := device.get("endpointId"))
    ]


def validate_websocket_response(response: dict[str, Any], *, endpoint: str) -> None:
    """Validate a relay acknowledgement and any per-device statuses."""
    _validate_status(response, endpoint)
    data = response.get("data")
    if not isinstance(data, dict):
        return
    device_list = data.get("devList")
    if not isinstance(device_list, list):
        return
    for item in device_list:
        if isinstance(item, dict):
            _validate_status(item, endpoint)


def _validate_status(response: dict[str, Any], endpoint: str) -> None:
    """Validate one relay status object."""
    raise_for_cloud_response(response, endpoint=endpoint)
    if response.get("status") not in SUCCESS_STATUSES:
        raise AuxServerError("Invalid AUX websocket response", endpoint=endpoint)


def extract_websocket_updates(
    message: dict[str, Any],
) -> tuple[DeviceUpdate, ...]:
    """Extract endpoint param updates from websocket messages."""
    msgtype = message.get("msgtype")
    data = message.get("data") or {}
    if not isinstance(data, dict):
        return ()
    updates: list[DeviceUpdate] = []

    if msgtype in {"subk", "subresetk"} and message.get("status") in SUCCESS_STATUSES:
        updates.extend(_extract_devlist_updates(data))

    if msgtype == "push" and message.get("topic") == "devpush":
        updates.extend(_extract_devlist_updates(data))
        updates.extend(_extract_push_payload_update(data))

    if msgtype == "transit.opencontrolk":
        updates.extend(_extract_opencontrol_updates(data))

    return tuple(
        update for update in updates if update.params or update.available is False
    )


def _extract_devlist_updates(data: dict[str, Any]) -> list[DeviceUpdate]:
    """Extract updates from websocket data.devList."""
    updates: list[DeviceUpdate] = []
    device_list = data.get("devList")
    if not isinstance(device_list, list):
        return updates
    for item in device_list:
        if not isinstance(item, dict):
            continue
        params = decode_json_payload(item.get("data"))
        endpoint_id = item.get("endpointId") or params.get("did")
        if (
            isinstance(endpoint_id, str)
            and endpoint_id
            and params
            and item.get("status") in SUCCESS_STATUSES
        ):
            updates.append(_build_update(endpoint_id, params))
    return updates


def _extract_push_payload_update(data: dict[str, Any]) -> list[DeviceUpdate]:
    """Extract updates from push/devpush payload variants."""
    updates: list[DeviceUpdate] = []
    endpoint_id = data.get("endpointId")
    nested_payload = data.get("payload")
    nested_data = (
        nested_payload.get("data") if isinstance(nested_payload, dict) else None
    )

    for payload in (
        data.get("data"),
        nested_data,
    ):
        params = decode_json_payload(payload)
        update_endpoint_id = endpoint_id or params.get("did")
        if isinstance(update_endpoint_id, str) and update_endpoint_id and params:
            updates.append(_build_update(update_endpoint_id, params))
    return updates


def _build_update(endpoint_id: str, params: dict[str, Any]) -> DeviceUpdate:
    """Build one websocket update, preserving explicit offline state."""
    available = _extract_availability(params)
    return DeviceUpdate(
        endpoint_id=endpoint_id,
        params={} if available is False else params,
        available=available,
    )


def _extract_availability(params: dict[str, Any]) -> bool | None:
    """Extract explicit device availability from websocket payload params."""
    online = params.get("online")
    if isinstance(online, bool):
        return online

    state = params.get("state")
    if state in (0, "0", False):
        return False
    if state in (1, "1", True):
        return True
    return None


def _extract_opencontrol_updates(data: dict[str, Any]) -> list[DeviceUpdate]:
    """Extract updates from transit.opencontrolk responseList."""
    updates: list[DeviceUpdate] = []
    response_list = data.get("responseList")
    if not isinstance(response_list, list):
        return updates
    for item in response_list:
        if not isinstance(item, dict):
            continue
        event = item.get("event") or {}
        if not isinstance(event, dict):
            continue
        endpoint = event.get("endpoint")
        endpoint_id = endpoint.get("endpointId") if isinstance(endpoint, dict) else None
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        status = payload.get("status", 0)
        try:
            params = parse_std_data(payload.get("data"))
        except (TypeError, ValueError):
            continue
        if (
            isinstance(endpoint_id, str)
            and endpoint_id
            and params
            and status in SUCCESS_STATUSES
        ):
            updates.append(DeviceUpdate(endpoint_id, params))
    return updates
