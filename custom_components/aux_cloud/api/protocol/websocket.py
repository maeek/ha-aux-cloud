"""WebSocket protocol parsing for AUX Cloud."""

from __future__ import annotations

from .common import decode_json_payload, parse_std_data


def extract_websocket_updates(message: dict) -> list[dict]:
    """Extract endpoint param updates from websocket messages."""
    msgtype = message.get("msgtype")
    data = message.get("data") or {}
    updates: list[dict] = []

    if msgtype in {"subk", "subresetk"}:
        updates.extend(_extract_devlist_updates(data))

    if msgtype == "push" and message.get("topic") == "devpush":
        updates.extend(_extract_devlist_updates(data))
        updates.extend(_extract_push_payload_update(data))

    if msgtype == "transit.opencontrolk":
        updates.extend(_extract_opencontrol_updates(data))

    return [
        update
        for update in updates
        if update.get("params") or update.get("available") is False
    ]


def _extract_devlist_updates(data: dict) -> list[dict]:
    """Extract updates from websocket data.devList."""
    updates = []
    for item in data.get("devList", []) or []:
        params = decode_json_payload(item.get("data"))
        endpoint_id = item.get("endpointId") or params.get("did")
        if endpoint_id and params:
            updates.append(_build_update(endpoint_id, params, item.get("status", 0)))
    return updates


def _extract_push_payload_update(data: dict) -> list[dict]:
    """Extract updates from push/devpush payload variants."""
    updates = []
    endpoint_id = data.get("endpointId")

    for payload in (
        data.get("data"),
        (data.get("payload") or {}).get("data"),
    ):
        params = decode_json_payload(payload)
        update_endpoint_id = endpoint_id or params.get("did")
        if update_endpoint_id and params:
            updates.append(_build_update(update_endpoint_id, params, 0))
    return updates


def _build_update(endpoint_id: str, params: dict, status) -> dict:
    """Build one websocket update, preserving explicit offline state."""
    available = _extract_availability(params)
    update = {
        "endpointId": endpoint_id,
        "params": {} if available is False else params,
        "status": status,
    }
    if available is not None:
        update["available"] = available
    return update


def _extract_availability(params: dict) -> bool | None:
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


def _extract_opencontrol_updates(data: dict) -> list[dict]:
    """Extract updates from transit.opencontrolk responseList."""
    updates = []
    for item in data.get("responseList", []) or []:
        event = item.get("event") or {}
        endpoint_id = (event.get("endpoint") or {}).get("endpointId")
        payload = event.get("payload") or {}
        status = payload.get("status", 0)
        params = parse_std_data(payload.get("data"))
        if endpoint_id and params and status in (None, 0):
            updates.append(
                {
                    "endpointId": endpoint_id,
                    "params": params,
                    "status": status,
                }
            )
    return updates
