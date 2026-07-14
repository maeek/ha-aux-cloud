"""Authenticated AUX Cloud HTTP session tests."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import custom_components.aux_cloud.api.session as session_module
from custom_components.aux_cloud.api import AuxAuthError, AuxSessionExpired
from custom_components.aux_cloud.api.models import AuxCredentials
from custom_components.aux_cloud.api.session import AuxCloudSession


def _session(region="eu"):
    return AuxCloudSession(region=region, session=MagicMock(closed=False))


def _login_payload(session):
    return json.loads(session.make_request.call_args.kwargs["data_raw"].decode())


async def test_email_and_phone_login_payloads_match_the_app(monkeypatch):
    """Credential kinds use distinct, APK-compatible wire fields."""
    monkeypatch.setattr(session_module, "_encrypt_login_payload", lambda _i, _k, d: d)
    session = _session()
    session.make_request = AsyncMock(
        return_value={"status": 0, "loginsession": "session", "userid": "user"}
    )

    await session.login(AuxCredentials.email("user@example.com", "secret"))
    assert list(_login_payload(session)) == ["email", "password", "companyid", "lid"]
    await session.login(AuxCredentials.phone("13800138000", "secret"))
    payload = _login_payload(session)
    assert list(payload) == ["phone", "password", "companyid", "lid"]
    assert payload["phone"] == "13800138000"
    assert session._credentials == AuxCredentials.phone("13800138000", "secret")


async def test_expired_sessions_recover_once_and_bad_credentials_surface():
    """A request gets one fresh login attempt and never loops on rejected credentials."""
    session = _session()
    session._credentials = AuxCredentials.email("user@example.com", "secret")
    calls = []

    async def request_once(**kwargs):
        endpoint = kwargs["endpoint"]
        calls.append(endpoint)
        if endpoint == "account/login":
            return {"status": 0, "loginsession": "fresh", "userid": "user"}
        if calls.count("device/query") == 1:
            raise AuxSessionExpired(code=-1000)
        return {"status": 0}

    session._request_once = AsyncMock(side_effect=request_once)
    assert await session.make_request("device/query") == {"status": 0}
    assert calls == ["device/query", "account/login", "device/query"]

    async def rejected(**kwargs):
        if kwargs["endpoint"] == "account/login":
            return {"status": -1006}
        raise AuxSessionExpired(code=-1000)

    session._request_once.side_effect = rejected
    with pytest.raises(AuxAuthError):
        await session.make_request("device/query")
