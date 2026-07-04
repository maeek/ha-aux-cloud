"""AUX Cloud HTTP session and authentication helpers."""

# pylint: disable=too-many-arguments

from __future__ import annotations

import hashlib
import json
import logging
import time

import aiohttp

from .errors import (
    AuxApiError,
    AuxAuthError,
    AuxNetworkError,
    AuxServerError,
    raise_for_cloud_response,
    raise_for_http_status,
    should_recover_session,
)
from .util import encrypt_aes_cbc_zero_padding

TIMESTAMP_TOKEN_ENCRYPT_KEY = "kdixkdqp54545^#*"
PASSWORD_ENCRYPT_KEY = "4969fj#k23#"
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


class AuxCloudSession:
    """AUX Cloud authenticated HTTP session wrapper."""

    def __init__(
        self, region: str = "eu", session: aiohttp.ClientSession | None = None
    ) -> None:
        """Initialize the session wrapper."""
        self.url = {
            "eu": API_SERVER_URL_EU,
            "usa": API_SERVER_URL_USA,
            "cn": API_SERVER_URL_CN,
            "rus": API_SERVER_URL_RUS,
        }.get(region, API_SERVER_URL_EU)
        self.region = region
        self.email: str | None = None
        self.phone_number: str | None = None
        self.phone_country_code: str | None = None
        self.password: str | None = None
        self.loginsession: str | None = None
        self.userid: str | None = None
        self._session = session

    def get_headers(self, **kwargs: str) -> dict:
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

    async def make_request(
        self,
        method: str,
        endpoint: str,
        headers: dict = None,
        data: dict = None,
        data_raw: str | bytes = None,
        params: dict = None,
        ssl: bool = False,
        recover_session: bool = True,
    ) -> dict:
        """Make an HTTP request and parse JSON response data."""
        url = f"{self.url}/{endpoint}"
        request_kwargs = {
            "method": method,
            "url": url,
            "endpoint": endpoint,
            "headers": headers,
            "data": data,
            "data_raw": data_raw,
            "params": params,
            "ssl": ssl,
        }

        _LOGGER.debug("Making %s request to %s", method, endpoint)

        try:
            if self._session is not None:
                return await self._request_once(self._session, **request_kwargs)

            async with aiohttp.ClientSession() as session:
                return await self._request_once(session, **request_kwargs)
        except AuxApiError as exc:
            if (
                recover_session
                and endpoint != "account/login"
                and should_recover_session(exc)
            ):
                _LOGGER.debug("AUX Cloud session expired; attempting silent re-login")
                await self.recover_session()
                return await self.make_request(
                    method=method,
                    endpoint=endpoint,
                    headers=(
                        self.get_headers(
                            **{
                                key: value
                                for key, value in (headers or {}).items()
                                if key.lower()
                                not in {
                                    "loginsession",
                                    "userid",
                                }
                            }
                        )
                        if headers is not None
                        else None
                    ),
                    data=data,
                    data_raw=data_raw,
                    params=params,
                    ssl=ssl,
                    recover_session=False,
                )
            raise

    async def _request_once(
        self,
        session: aiohttp.ClientSession,
        *,
        method: str,
        url: str,
        endpoint: str,
        headers: dict | None,
        data: dict | None,
        data_raw: str | bytes | None,
        params: dict | None,
        ssl: bool,
    ) -> dict:
        """Perform one HTTP request without session recovery."""
        request_data = (
            data_raw
            if data_raw
            else json.dumps(data, separators=(",", ":")) if data else None
        )

        try:
            async with session.request(
                method=method,
                url=url,
                headers=headers,
                data=request_data,
                params=params,
                ssl=ssl,
            ) as response:
                response_text = await response.text()
                raise_for_http_status(
                    response.status,
                    endpoint=endpoint,
                    response=response_text,
                )
                try:
                    json_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError as exc:
                    raise AuxServerError(
                        "AUX Cloud returned invalid JSON",
                        http_status=response.status,
                        endpoint=endpoint,
                        response=response_text,
                    ) from exc

                raise_for_cloud_response(json_data, endpoint=endpoint)
                return json_data
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise AuxNetworkError(endpoint=endpoint) from exc

    async def login(
        self,
        email: str = None,
        password: str = None,
        *,
        phone_number: str = None,
        phone_country_code: str = None,
    ) -> bool:
        """Login to AUX Cloud services."""
        password = password if password is not None else self.password
        use_phone_login = phone_number is not None or self.phone_number is not None

        if use_phone_login:
            phone_number = (
                phone_number if phone_number is not None else self.phone_number
            )
            phone_country_code = (
                phone_country_code
                if phone_country_code is not None
                else self.phone_country_code
            )
            if not phone_number or not phone_country_code or password is None:
                raise AuxAuthError(
                    "Missing AUX Cloud phone credentials",
                    endpoint="account/login",
                )
        else:
            email = email if email is not None else self.email
            if email is None or password is None:
                raise AuxAuthError(
                    "Missing AUX Cloud credentials",
                    endpoint="account/login",
                )

        self.password = password

        current_time = time.time()
        sha_password = hashlib.sha1(
            f"{password}{PASSWORD_ENCRYPT_KEY}".encode()
        ).hexdigest()
        if use_phone_login:
            self.email = None
            self.phone_number = phone_number
            self.phone_country_code = phone_country_code
            payload = {
                "username": phone_number,
                "password": sha_password,
                "countrycode": phone_country_code,
                "companyid": COMPANY_ID,
                "lid": LICENSE_ID,
            }
        else:
            self.email = email
            self.phone_number = None
            self.phone_country_code = None
            payload = {
                "email": email,
                "password": sha_password,
                "companyid": COMPANY_ID,
                "lid": LICENSE_ID,
            }
        json_payload = json.dumps(payload, separators=(",", ":"))

        token = hashlib.md5(f"{json_payload}{BODY_ENCRYPT_KEY}".encode()).hexdigest()
        md5 = hashlib.md5(
            f"{current_time}{TIMESTAMP_TOKEN_ENCRYPT_KEY}".encode()
        ).digest()

        json_data = await self.make_request(
            method="POST",
            endpoint="account/login",
            headers=self.get_headers(timestamp=f"{current_time}", token=token),
            data_raw=encrypt_aes_cbc_zero_padding(
                AES_INITIAL_VECTOR, md5, json_payload.encode()
            ),
            ssl=False,
            recover_session=False,
        )

        if "status" in json_data and json_data["status"] == 0:
            self.loginsession = json_data["loginsession"]
            self.userid = json_data["userid"]
            _LOGGER.debug("Login successful: %s", self.userid)
            return True

        raise_for_cloud_response(json_data, endpoint="account/login")
        raise AuxAuthError(
            "AUX Cloud login response did not include a session",
            endpoint="account/login",
            response=json_data,
        )

    async def recover_session(self) -> bool:
        """Recover an expired session by logging in again with stored credentials."""
        if not self.password or not (self.email or self.phone_number):
            raise AuxAuthError("Cannot recover AUX Cloud session without credentials")
        if self.phone_number:
            return await self.login(
                password=self.password,
                phone_number=self.phone_number,
                phone_country_code=self.phone_country_code,
            )
        return await self.login(self.email, self.password)

    def is_logged_in(self) -> bool:
        """Return whether the session has active login identifiers."""
        return self.loginsession is not None and self.userid is not None
