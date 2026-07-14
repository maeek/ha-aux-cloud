"""AUX Cloud HTTP session and authentication helpers."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Mapping
from typing import Any, cast

import aiohttp
from Crypto.Cipher import AES

from .errors import (
    AuxApiError,
    AuxAuthError,
    AuxNetworkError,
    AuxServerError,
    raise_for_cloud_response,
    raise_for_http_status,
    should_recover_session,
)
from .models import AuxCredentials

TIMESTAMP_TOKEN_ENCRYPT_KEY = "kdixkdqp54545^#*"  # noqa: S105
PASSWORD_ENCRYPT_KEY = "4969fj#k23#"  # noqa: S105
BODY_ENCRYPT_KEY = "xgx3d*fe3478$ukx"

AES_INITIAL_VECTOR = bytes(
    [
        (byte + 256) % 256
        for byte in [
            -22,
            -86,
            -86,
            58,
            -69,
            88,
            98,
            -94,
            25,
            24,
            -75,
            119,
            29,
            22,
            21,
            -86,
        ]
    ]
)

# pylint: disable=line-too-long
LICENSE = "PAFbJJ3WbvDxH5vvWezXN5BujETtH/iuTtIIW5CE/SeHN7oNKqnEajgljTcL0fBQQWM0XAAAAAAnBhJyhMi7zIQMsUcwR/PEwGA3uB5HLOnr+xRrci+FwHMkUtK7v4yo0ZHa+jPvb6djelPP893k7SagmffZmOkLSOsbNs8CAqsu8HuIDs2mDQAAAAA="
# pylint: enable=line-too-long
LICENSE_ID = "3c015b249dd66ef0f11f9bef59ecd737"
COMPANY_ID = "48eb1b36cf0202ab2ef07b880ecda60d"

SPOOF_APP_VERSION = "2.2.10.456537160"
SPOOF_USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 12; SM-G991B Build/SP1A.210812.016)"
SPOOF_SYSTEM = "android"
SPOOF_APP_PLATFORM = "android"

API_SERVER_URL_EU = "https://app-service-deu-f0e9ebbb.smarthomecs.de"
API_SERVER_URL_USA = "https://app-service-usa-fd7cc04c.smarthomecs.com"
API_SERVER_URL_CN = "https://app-service-chn-31a93883.ibroadlink.com"
API_SERVER_URL_RUS = "https://app-service-rus-b8bbc3be.smarthomecs.com"

_LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)


def _encrypt_login_payload(iv: bytes, key: bytes, data: bytes) -> bytes:
    """Encrypt a vendor login payload using its required zero padding."""
    padding = b"\x00" * (AES.block_size - len(data) % AES.block_size)
    return AES.new(key, AES.MODE_CBC, iv).encrypt(data + padding)


class AuxCloudSession:
    """AUX Cloud authenticated HTTP session wrapper."""

    def __init__(self, region: str, session: aiohttp.ClientSession) -> None:
        """Initialize the session wrapper."""
        self.url = {
            "eu": API_SERVER_URL_EU,
            "usa": API_SERVER_URL_USA,
            "cn": API_SERVER_URL_CN,
            "rus": API_SERVER_URL_RUS,
        }.get(region, API_SERVER_URL_EU)
        self.region = region
        self._credentials: AuxCredentials | None = None
        self.loginsession: str | None = None
        self.userid: str | None = None
        self._session = session
        self._login_lock = asyncio.Lock()

    def get_headers(self, **kwargs: str) -> dict[str, str]:
        """Return AUX Cloud app headers."""
        return {
            "Content-Type": "application/x-java-serialized-object",
            "licenseId": LICENSE_ID,
            "lid": LICENSE_ID,
            "language": "en",
            "appVersion": SPOOF_APP_VERSION,
            "User-Agent": SPOOF_USER_AGENT,
            "system": SPOOF_SYSTEM,
            "appPlatform": SPOOF_APP_PLATFORM,
            "loginsession": self.loginsession or "",
            "userid": self.userid or "",
            **kwargs,
        }

    @property
    def websession(self) -> aiohttp.ClientSession:
        """Return the injected Home Assistant web session."""
        return self._session

    async def make_request(
        self,
        endpoint: str,
        *,
        header_overrides: Mapping[str, str] | None = None,
        data: dict[str, Any] | None = None,
        data_raw: str | bytes | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make one POST request with at most one session recovery attempt."""
        url = f"{self.url}/{endpoint}"
        session_at_request = self.loginsession
        _LOGGER.debug("Making POST request to %s", endpoint)

        for attempt in range(2):
            try:
                return await self._request_once(
                    url=url,
                    endpoint=endpoint,
                    headers=self.get_headers(**dict(header_overrides or {})),
                    data=data,
                    data_raw=data_raw,
                    params=params,
                )
            except AuxApiError as exc:
                if (
                    attempt > 0
                    or endpoint == "account/login"
                    or not should_recover_session(exc)
                ):
                    raise
                _LOGGER.debug("AUX Cloud session expired; attempting silent re-login")
                await self.recover_session(expired_session=session_at_request)

        raise RuntimeError("Unreachable AUX Cloud request state")

    async def _request_once(
        self,
        *,
        url: str,
        endpoint: str,
        headers: dict[str, str],
        data: dict[str, Any] | None,
        data_raw: str | bytes | None,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Perform one HTTP request without session recovery."""
        request_data = (
            data_raw
            if data_raw is not None
            else json.dumps(data, separators=(",", ":"))
            if data
            else None
        )

        try:
            async with self._session.request(
                method="POST",
                url=url,
                headers=headers,
                data=request_data,
                params=params,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                response_text = await response.text()
                raise_for_http_status(
                    response.status,
                    endpoint=endpoint,
                    retry_after=response.headers.get("Retry-After"),
                )
                try:
                    json_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError as exc:
                    raise AuxServerError(
                        "AUX Cloud returned invalid JSON",
                        http_status=response.status,
                        endpoint=endpoint,
                    ) from exc

                raise_for_cloud_response(json_data, endpoint=endpoint)
                return cast(dict[str, Any], json_data)
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise AuxNetworkError(endpoint=endpoint) from exc

    async def login(self, credentials: AuxCredentials) -> None:
        """Login to AUX Cloud services."""
        async with self._login_lock:
            await self._login_unlocked(credentials)

    async def _login_unlocked(self, credentials: AuxCredentials) -> None:
        """Log in while the single-flight authentication lock is held."""
        current_time = time.time()
        sha_password = hashlib.sha1(
            f"{credentials.password}{PASSWORD_ENCRYPT_KEY}".encode(),
            usedforsecurity=False,
        ).hexdigest()
        if credentials.kind == "phone":
            payload = {
                "phone": credentials.username,
                "password": sha_password,
                "companyid": COMPANY_ID,
                "lid": LICENSE_ID,
            }
        else:
            payload = {
                "email": credentials.username,
                "password": sha_password,
                "companyid": COMPANY_ID,
                "lid": LICENSE_ID,
            }
        json_payload = json.dumps(payload, separators=(",", ":"))

        token = hashlib.md5(
            f"{json_payload}{BODY_ENCRYPT_KEY}".encode(), usedforsecurity=False
        ).hexdigest()
        md5 = hashlib.md5(
            f"{current_time}{TIMESTAMP_TOKEN_ENCRYPT_KEY}".encode(),
            usedforsecurity=False,
        ).digest()

        json_data = await self.make_request(
            endpoint="account/login",
            header_overrides={"timestamp": f"{current_time}", "token": token},
            data_raw=_encrypt_login_payload(
                AES_INITIAL_VECTOR, md5, json_payload.encode()
            ),
        )

        self._store_login_identity(json_data, credentials)

    def _store_login_identity(
        self, json_data: dict[str, Any], credentials: AuxCredentials
    ) -> None:
        """Validate and store one successful login response."""
        if json_data.get("status") != 0:
            raise_for_cloud_response(json_data, endpoint="account/login")
        login_session = json_data.get("loginsession")
        user_id = json_data.get("userid")
        if not isinstance(login_session, str) or not isinstance(user_id, str):
            raise AuxServerError(
                "AUX Cloud login response did not include an identity",
                endpoint="account/login",
            )
        self.loginsession = login_session
        self.userid = user_id
        self._credentials = credentials
        _LOGGER.debug("AUX Cloud login successful")

    async def recover_session(self, *, expired_session: str | None = None) -> None:
        """Recover an expired session by logging in again with stored credentials."""
        async with self._login_lock:
            if self.is_logged_in() and (
                expired_session is None or self.loginsession != expired_session
            ):
                return
            self.loginsession = None
            self.userid = None
            if self._credentials is None:
                raise AuxAuthError(
                    "Cannot recover AUX Cloud session without credentials"
                )
            await self._login_unlocked(self._credentials)

    def is_logged_in(self) -> bool:
        """Return whether the session has active login identifiers."""
        return self.loginsession is not None and self.userid is not None
