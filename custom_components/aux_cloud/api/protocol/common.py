"""Shared AUX Cloud control protocol helpers."""

from __future__ import annotations

import base64
import json
import time
from typing import Any


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
    values: dict[str, Any],
) -> tuple[list[str], list[list[dict]]]:
    """Convert a param/value mapping into the AUX key-value control payload shape."""
    return list(values.keys()), [
        [{"idx": 1, "val": value}] for value in values.values()
    ]


def build_device_params_directive(
    device: dict,
    act: str,
    params: list[str] | None = None,
    vals: list | None = None,
) -> dict[str, Any]:
    """Build a KeyValueControl directive for HTTP or websocket transport."""
    if params is None:
        params = []
    if vals is None:
        vals = []

    if act == "set" and len(params) != len(vals):
        raise ValueError("Params and Vals must have the same length")

    cookie = json.loads(base64.b64decode(device["cookie"].encode()))
    mapped_cookie = base64.b64encode(
        json.dumps(
            {
                "device": {
                    "id": cookie["terminalid"],
                    "key": cookie["aeskey"],
                    "devSession": device["devSession"],
                    "aeskey": cookie["aeskey"],
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

    directive = {
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


def parse_std_data(data: str | dict | None) -> dict:
    """Parse Broadlink std data into a param dictionary."""
    if not data:
        return {}

    response = json.loads(data) if isinstance(data, str) else data
    if not isinstance(response, dict):
        return {}

    if "params" not in response or "vals" not in response:
        return dict(response)

    response_dict = {}
    for index, param in enumerate(response.get("params", [])):
        vals = response.get("vals", [])
        try:
            response_dict[param] = vals[index][0]["val"]
        except (IndexError, KeyError, TypeError):
            continue
    return response_dict


def decode_json_payload(value) -> dict:
    """Decode a websocket payload value into a dict."""
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value:
        return {}

    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    except json.JSONDecodeError:
        pass

    try:
        decoded = base64.b64decode(value).decode().strip()
        parsed = json.loads(decoded)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    try:
        decoded = bytes.fromhex(value).decode().strip()
        parsed = json.loads(decoded)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:  # pylint: disable=broad-exception-caught
        return {}
