"""Decode AUX device metadata and resolve protocol versions."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from typing import Any, Final, cast

from .api.models import AuxDevice

AUX_PROTOCOL_VERSION: Final = "_aux_protocol_version"
AUX_QUERY_FAILURES: Final = "_aux_query_failures"

_MAX_COOKIE_BYTES = 512 * 1024
_MAX_COOKIE_PROFILE_PARAMS = 512
_MAX_COOKIE_PARAM_LENGTH = 128


def decode_device_cookie(value: object) -> dict[str, Any] | None:
    """Decode a bounded AUX cookie without exposing its sensitive contents."""
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


def get_protocol_version(device: Mapping[str, Any]) -> int | None:
    """Return the effective device protocol version without guessing."""
    return get_protocol_version_details(device)[0]


def get_protocol_version_details(
    device: Mapping[str, Any],
) -> tuple[int | None, str | None]:
    """Resolve protocol metadata and identify its non-sensitive source."""
    # A session value is populated only after a device response confirms that
    # extern/cookie metadata is stale. That direct observation must win thereafter.
    if version := _validated_protocol_version(device.get(AUX_PROTOCOL_VERSION)):
        return version, "session"

    external = _decode_metadata_object(device.get("extern"))
    if external is not None and (
        version := _validated_protocol_version(external.get("ver"))
    ):
        return version, "extern"

    cookie = decode_device_cookie(device.get("cookie"))
    extend = (
        _decode_metadata_object(cookie.get("extend")) if cookie is not None else None
    )
    if extend is not None and (
        version := _validated_protocol_version(extend.get("ver"))
    ):
        return version, "cookie_extend"

    params = device.get("params")
    if isinstance(params, Mapping) and (
        version := _validated_protocol_version(params.get("ver"))
    ):
        return version, "response"
    return None, None


def set_protocol_version(device: AuxDevice, version: Any) -> None:
    """Store a successfully resolved protocol version on the runtime snapshot."""
    if resolved := _validated_protocol_version(version):
        device[AUX_PROTOCOL_VERSION] = resolved


def get_cookie_profile_params(device: Mapping[str, Any]) -> tuple[str, ...]:
    """Return bounded product-interface names embedded in a device cookie."""
    cookie = decode_device_cookie(device.get("cookie"))
    profile = (
        _decode_metadata_object(cookie.get("profile")) if cookie is not None else None
    )
    if profile is None:
        return ()
    suids = profile.get("suids")
    if not isinstance(suids, list):
        return ()

    params: set[str] = set()
    for suid in suids:
        if not isinstance(suid, Mapping):
            continue
        interfaces = suid.get("intfs")
        if not isinstance(interfaces, Mapping):
            continue
        for param in interfaces:
            if isinstance(param, str) and 0 < len(param) <= _MAX_COOKIE_PARAM_LENGTH:
                params.add(param)
                if len(params) > _MAX_COOKIE_PROFILE_PARAMS:
                    return ()
    return tuple(sorted(params))


def _decode_metadata_object(value: Any) -> Mapping[str, Any] | None:
    """Return an object supplied either directly or as JSON text."""
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _validated_protocol_version(value: Any) -> int | None:
    """Return a positive integral numeric protocol version."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)
    return None
