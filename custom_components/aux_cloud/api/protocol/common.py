"""Shared AUX Cloud control protocol helpers."""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import time
from collections.abc import Mapping
from typing import Any, cast

from ..errors import AuxDeviceError, AuxServerError, raise_for_cloud_response
from ..models import AuxDevice

_CONTROL_ENDPOINT = "device/control/v2/sdkcontrol"
_MAX_COOKIE_BYTES = 512 * 1024


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


def decode_device_cookie(value: object) -> dict[str, Any] | None:
    """Decode a bounded AUX cookie without logging its sensitive contents."""
    if not isinstance(value, str):
        return None
    encoded = value.strip()
    if not encoded or len(encoded) > (_MAX_COOKIE_BYTES * 4 // 3) + 4:
        return None
    encoded += "=" * (-len(encoded) % 4)
    try:
        decoded = base64.b64decode(encoded, validate=True)
        if len(decoded) > _MAX_COOKIE_BYTES:
            return None
        payload = json.loads(decoded.decode())
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else None


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
