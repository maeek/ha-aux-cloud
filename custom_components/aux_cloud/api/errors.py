"""Structured AUX Cloud API errors and response decoding."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

SUCCESS_STATUSES = {None, 0, "0"}

BAD_CREDENTIAL_CODES = {-1006, -1008, -1020, -1033, -1035, -1037}
SESSION_EXPIRED_CODES = {-30129, -1000, -1009, -1012, -3003, -49009, 10011}
NETWORK_ERROR_CODES = {
    -3004,
    -3006,
    -3114,
    -4000,
    -4013,
    -4037,
    -4038,
    -4041,
    -49001,
}
SERVER_ERROR_CODES = {-1099, -3005, -49002}
RATE_LIMIT_ERROR_CODES = {-2001, -1036}
DEVICE_ERROR_CODES = {
    -49025,
    -3,
    -7,
    -3103,
    -3118,
    -4012,
    -4028,
    -4044,
    -4045,
    -4046,
}

ERROR_CODE_MESSAGES = {
    -3: "AUX Cloud device is unavailable",
    -7: "AUX Cloud device command failed",
    -49025: "AUX Cloud device does not support this parameter query",
    -1000: "Invalid AUX Cloud session",
    -1006: "AUX Cloud account or password is incorrect",
    -1009: "AUX Cloud login is required",
    -1012: "AUX Cloud login is required again",
    -1036: "AUX Cloud requests are too frequent",
    -3003: "AUX Cloud account is not logged in",
    -3004: "AUX Cloud HTTP request failed",
    -3006: "AUX Cloud server did not return a response",
    -3114: "AUX Cloud DNS resolution failed",
    -4000: "AUX Cloud network request timed out",
    -4013: "AUX Cloud domain name resolution failed",
    -4037: "AUX Cloud SSL connection failed",
    -4038: "AUX Cloud SSL handshake failed",
    -4041: "AUX Cloud network is unavailable",
    -49001: "AUX Cloud network error",
    -49002: "AUX Cloud server error",
    -49009: "AUX Cloud authentication failed",
    -30129: "AUX Cloud login session expired",
    10011: "AUX Cloud login session expired",
}


class AuxApiError(Exception):
    """Base exception raised for AUX Cloud API failures."""

    translation_key = "unknown"
    config_flow_key = "unknown"
    default_message = "AUX Cloud API error"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: int | None = None,
        http_status: int | None = None,
        endpoint: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        """Initialize an AUX Cloud API error."""
        self.code = code
        self.http_status = http_status
        self.endpoint = endpoint
        self.retry_after = retry_after
        super().__init__(message or self._format_message())

    def _format_message(self) -> str:
        """Return a concise diagnostic message."""
        message = (
            ERROR_CODE_MESSAGES.get(self.code, self.default_message)
            if self.code is not None
            else self.default_message
        )
        details = []
        if self.code is not None:
            details.append(f"code {self.code}")
        if self.http_status is not None:
            details.append(f"HTTP {self.http_status}")
        if self.endpoint:
            details.append(f"endpoint {self.endpoint}")
        return f"{message} ({', '.join(details)})" if details else message


class AuxAuthError(AuxApiError):
    """Raised when AUX Cloud rejects stored credentials."""

    translation_key = "invalid_auth"
    config_flow_key = "bad_credentials"
    default_message = "AUX Cloud authentication failed"


class AuxSessionExpired(AuxApiError):
    """Raised when the current AUX Cloud login session is no longer valid."""

    translation_key = "session_expired"
    config_flow_key = "session_expired"
    default_message = "AUX Cloud session expired"


class AuxNetworkError(AuxApiError):
    """Raised when the AUX Cloud request cannot reach the network/server."""

    translation_key = "cannot_connect"
    config_flow_key = "cannot_connect"
    default_message = "AUX Cloud network error"


class AuxServerError(AuxApiError):
    """Raised when the AUX Cloud service returns an unavailable/server error."""

    translation_key = "api_unavailable"
    config_flow_key = "api_unavailable"
    default_message = "AUX Cloud server error"


class AuxRateLimitError(AuxApiError):
    """Raised when AUX Cloud throttles the request."""

    translation_key = "rate_limited"
    config_flow_key = "rate_limited"
    default_message = "AUX Cloud rate limit reached"


class AuxDeviceError(AuxApiError):
    """Raised when a device-level AUX Cloud command fails."""

    translation_key = "device_error"
    default_message = "AUX Cloud device command failed"


class AuxUnknownApiError(AuxApiError):
    """Raised for an AUX Cloud error code that is not yet classified."""

    translation_key = "unknown"
    default_message = "Unknown AUX Cloud API error"


def raise_for_http_status(
    status: int,
    *,
    endpoint: str | None = None,
    retry_after: str | None = None,
) -> None:
    """Raise a typed error for an unsuccessful HTTP status."""
    if status < 400:
        return

    if status in (401, 403):
        raise AuxSessionExpired(
            http_status=status,
            endpoint=endpoint,
        )
    if status == 429:
        raise AuxRateLimitError(
            http_status=status,
            endpoint=endpoint,
            retry_after=parse_retry_after(retry_after),
        )
    if status in (408, 425):
        raise AuxNetworkError(
            http_status=status,
            endpoint=endpoint,
        )
    if status >= 500:
        raise AuxServerError(
            http_status=status,
            endpoint=endpoint,
        )

    raise AuxUnknownApiError(
        http_status=status,
        endpoint=endpoint,
    )


def parse_retry_after(value: str | None) -> int | None:
    """Parse and clamp an HTTP Retry-After value to a safe HA backoff."""
    if not value:
        return None
    try:
        seconds = int(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            seconds = int((when - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None
    return max(1, min(seconds, 3600))


def raise_for_cloud_response(payload: Any, *, endpoint: str | None = None) -> None:
    """Raise a typed error when an AUX/BroadLink response contains an error code."""
    code = extract_error_code(payload)
    if code is None:
        return

    error_cls = error_class_for_code(code)
    raise error_cls(code=code, endpoint=endpoint)


def extract_error_code(payload: Any) -> int | None:
    """Extract the first non-success AUX/BroadLink status or code from a response."""
    if not isinstance(payload, dict):
        return None

    for path in (
        ("status",),
        ("code",),
        ("error",),
        ("errorCode",),
        ("errcode",),
        ("payload", "status"),
        ("payload", "code"),
        ("payload", "error"),
        ("event", "payload", "status"),
        ("event", "payload", "code"),
        ("event", "payload", "error"),
    ):
        code = _code_at_path(payload, path)
        if code is not None:
            return code

    for item in _response_list_items(payload):
        code = extract_error_code(item)
        if code is not None:
            return code

    return None


def error_class_for_code(code: int) -> type[AuxApiError]:
    """Return the typed exception class for an AUX/BroadLink error code."""
    error_classes = (
        (BAD_CREDENTIAL_CODES, AuxAuthError),
        (SESSION_EXPIRED_CODES, AuxSessionExpired),
        (RATE_LIMIT_ERROR_CODES, AuxRateLimitError),
        (NETWORK_ERROR_CODES, AuxNetworkError),
        (SERVER_ERROR_CODES, AuxServerError),
        (DEVICE_ERROR_CODES, AuxDeviceError),
    )
    for code_set, error_cls in error_classes:
        if code in code_set:
            return error_cls
    return AuxUnknownApiError


def should_recover_session(error: AuxApiError) -> bool:
    """Return whether a request should try one silent re-login."""
    return isinstance(error, AuxSessionExpired) or error.http_status in (401, 403)


def _code_at_path(payload: dict[str, Any], path: Iterable[str]) -> int | None:
    """Return a non-success integer code at a nested path."""
    current: Any = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return _coerce_error_code(current)


def _coerce_error_code(value: Any) -> int | None:
    """Convert a response value to a non-success integer error code."""
    if value in SUCCESS_STATUSES:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _response_list_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return nested websocket response-list event payloads."""
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return []
    items: list[dict[str, Any]] = []
    for item in data.get("responseList", []) or []:
        if isinstance(item, dict):
            event = item.get("event")
            items.append(event if isinstance(event, dict) else item)
    return items
