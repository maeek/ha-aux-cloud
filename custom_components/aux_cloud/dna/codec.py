"""Pure BroadLink DNA message encoding and decoding."""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import time
from collections.abc import Iterable, Mapping
from typing import Any, cast

from ..api.errors import (
    SUCCESS_STATUSES,
    AuxDeviceError,
    AuxServerError,
    raise_for_cloud_response,
)
from ..api.models import AuxDevice, DeviceUpdate
from ..device_metadata import decode_device_cookie

_CONTROL_ENDPOINT = "device/control/v2/sdkcontrol"


def build_directive_header(
    namespace: str, name: str, message_id_prefix: str, **kwargs: str
) -> dict[str, Any]:
    """Build a Broadlink DNA directive header."""
    timestamp = int(time.time())
    return {
        "namespace": namespace,
        "name": name,
        "interfaceVersion": "2",
        "senderId": "sdk",
        "messageId": f"{message_id_prefix}-{timestamp}",
        **kwargs,
    }


def device_values_to_params(
    values: Mapping[str, Any],
) -> tuple[list[str], list[list[dict[str, Any]]]]:
    """Convert a param/value mapping into the AUX key-value control payload shape."""
    return list(values.keys()), [
        [{"idx": 1, "val": value}] for value in values.values()
    ]


def build_device_params_directive(
    device: AuxDevice,
    act: str,
    params: list[str] | None = None,
    vals: list[Any] | None = None,
) -> dict[str, Any]:
    """Build a KeyValueControl directive for HTTP or websocket transport."""
    if params is None:
        params = []
    if vals is None:
        vals = []

    if act == "set" and len(params) != len(vals):
        raise ValueError("Params and Vals must have the same length")

    cookie = decode_device_cookie(device.get("cookie"))
    terminal_id = cookie.get("terminalid") if cookie is not None else None
    aes_key = cookie.get("aeskey") if cookie is not None else None
    if (
        not isinstance(terminal_id, (int, str))
        or isinstance(terminal_id, bool)
        or not str(terminal_id)
        or not isinstance(aes_key, str)
        or not aes_key
    ):
        raise AuxDeviceError(
            "AUX device cookie is missing required control metadata",
            endpoint=_CONTROL_ENDPOINT,
        )

    required_fields = (
        "endpointId",
        "productId",
        "mac",
        "devSession",
        "devicetypeFlag",
    )
    if missing_field := next(
        (field for field in required_fields if field not in device), None
    ):
        raise AuxDeviceError(
            f"AUX device metadata is missing {missing_field}",
            endpoint=_CONTROL_ENDPOINT,
        )

    mapped_cookie = base64.b64encode(
        json.dumps(
            {
                "device": {
                    "id": terminal_id,
                    "key": aes_key,
                    "devSession": device["devSession"],
                    "aeskey": aes_key,
                    "did": device["endpointId"],
                    "pid": device["productId"],
                    "mac": device["mac"],
                }
            },
            separators=(",", ":"),
        ).encode()
    ).decode()

    req_params = list(params)
    req_vals = list(vals)

    directive: dict[str, Any] = {
        "header": build_directive_header(
            namespace="DNA.KeyValueControl",
            name="KeyValueControl",
            message_id_prefix=device["endpointId"],
            timstamp=f"{int(time.time())}",
        ),
        "endpoint": {
            "devicePairedInfo": {
                "did": device["endpointId"],
                "pid": device["productId"],
                "mac": device["mac"],
                "devicetypeflag": device["devicetypeFlag"],
                "cookie": mapped_cookie,
            },
            "endpointId": device["endpointId"],
            "cookie": {},
            "devSession": device["devSession"],
        },
        "payload": {"act": act, "params": req_params, "vals": req_vals},
    }
    directive["payload"]["did"] = device["endpointId"]

    # Keep original integration behavior for single-param GET.
    if len(req_params) == 1 and act == "get":
        directive["payload"]["vals"] = [[{"val": 0, "idx": 1}]]

    return directive


def parse_std_data(
    data: str | dict[str, Any] | None,
) -> dict[str, Any]:
    """Parse Broadlink std data into a param dictionary."""
    if not data:
        return {}

    response = json.loads(data) if isinstance(data, str) else data
    if not isinstance(response, dict):
        return {}

    if "params" not in response or "vals" not in response:
        return dict(response)

    response_dict: dict[str, Any] = {}
    for index, param in enumerate(response.get("params", [])):
        vals = response.get("vals", [])
        try:
            response_dict[param] = vals[index][0]["val"]
        except (IndexError, KeyError, TypeError):
            continue
    return response_dict


def decode_json_payload(value: object) -> dict[str, Any]:
    """Decode a websocket payload value into a dict."""
    if isinstance(value, dict):
        return cast(dict[str, Any], dict(value))
    if not isinstance(value, str) or not value:
        return {}

    candidates = [value]
    with contextlib.suppress(binascii.Error, UnicodeDecodeError, ValueError):
        candidates.append(base64.b64decode(value, validate=True).decode().strip())
    with contextlib.suppress(UnicodeDecodeError, ValueError):
        candidates.append(bytes.fromhex(value).decode().strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
    return {}


def parse_control_event(event: dict[str, Any]) -> dict[str, Any]:
    """Parse a KeyValueControl event response."""
    raise_for_cloud_response(event, endpoint="device/control/v2/sdkcontrol")
    if event.get("header", {}).get("name") != "Response":
        raise AuxServerError(
            "Unexpected AUX device control response",
            endpoint="device/control/v2/sdkcontrol",
        )
    payload = event.get("payload", {})
    if not isinstance(payload, dict):
        raise AuxServerError(
            "Invalid AUX device control payload",
            endpoint="device/control/v2/sdkcontrol",
        )
    try:
        return parse_std_data(payload.get("data"))
    except (TypeError, ValueError) as exc:
        raise AuxServerError(
            "Invalid AUX device control data",
            endpoint="device/control/v2/sdkcontrol",
        ) from exc


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
    raise_for_cloud_response(response, endpoint=endpoint)
    if response.get("status") not in SUCCESS_STATUSES:
        raise AuxServerError("Invalid AUX websocket response", endpoint=endpoint)


def extract_websocket_updates(
    message: dict[str, Any],
) -> tuple[DeviceUpdate, ...]:
    """Extract endpoint parameter updates from websocket messages."""
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
    updates: list[DeviceUpdate] = []
    endpoint_id = data.get("endpointId")
    nested_payload = data.get("payload")
    nested_data = (
        nested_payload.get("data") if isinstance(nested_payload, dict) else None
    )
    for payload in (data.get("data"), nested_data):
        params = decode_json_payload(payload)
        update_endpoint_id = endpoint_id or params.get("did")
        if isinstance(update_endpoint_id, str) and update_endpoint_id and params:
            updates.append(_build_update(update_endpoint_id, params))
    return updates


def _build_update(endpoint_id: str, params: dict[str, Any]) -> DeviceUpdate:
    available = _extract_availability(params)
    return DeviceUpdate(
        endpoint_id=endpoint_id,
        params={} if available is False else params,
        available=available,
    )


def _extract_availability(params: dict[str, Any]) -> bool | None:
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
