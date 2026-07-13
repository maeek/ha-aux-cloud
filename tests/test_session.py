"""Focused AUX Cloud tests."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import custom_components.aux_cloud.api.session as session_module
from custom_components.aux_cloud.api import (
    AuxAuthError,
    AuxSessionExpired,
)
from custom_components.aux_cloud.api.errors import parse_retry_after
from custom_components.aux_cloud.api.models import AuxCredentials
from custom_components.aux_cloud.api.session import (
    REQUEST_TIMEOUT,
    AuxCloudSession,
)


def _decrypt_test_login_payload(call_args) -> dict:
    """Return the JSON login payload captured from a mocked request."""
    return json.loads(call_args.kwargs["data_raw"].decode())


def _session(region: str = "eu") -> AuxCloudSession:
    """Return an authenticated-session wrapper with an injected test client."""
    return AuxCloudSession(region=region, session=MagicMock(closed=False))


class TestAuxCloudAPI:
    """Tests for the AuxCloudAPI class."""

    async def test_email_login_payload_remains_email_payload(self, monkeypatch):
        """Test legacy email login still sends the original email-shaped payload."""
        session = _session()
        session.make_request = AsyncMock(
            return_value={"status": 0, "loginsession": "session", "userid": "user"}
        )
        monkeypatch.setattr(
            session_module,
            "_encrypt_login_payload",
            lambda _iv, _key, data: data,
        )

        assert (
            await session.login(AuxCredentials.email("user@example.com", "secret"))
            is None
        )

        payload = _decrypt_test_login_payload(session.make_request.call_args)
        assert list(payload) == ["email", "password", "companyid", "lid"]
        assert payload["email"] == "user@example.com"
        assert "username" not in payload
        assert session._credentials == AuxCredentials.email(
            "user@example.com", "secret"
        )

    async def test_phone_login_payload_uses_username_and_country_code(
        self, monkeypatch
    ):
        """Test phone login sends the phone-specific username payload."""
        session = _session(region="cn")
        session.make_request = AsyncMock(
            return_value={"status": 0, "loginsession": "session", "userid": "user"}
        )
        monkeypatch.setattr(
            session_module,
            "_encrypt_login_payload",
            lambda _iv, _key, data: data,
        )

        assert (
            await session.login(AuxCredentials.phone("13800138000", "secret")) is None
        )

        payload = _decrypt_test_login_payload(session.make_request.call_args)
        assert payload["username"] == "13800138000"
        assert payload["countrycode"] == ""
        assert "email" not in payload
        assert session._credentials == AuxCredentials.phone("13800138000", "secret")

    async def test_session_recovery_relogs_in_and_retries_request(self):
        """Test expired sessions trigger one silent credential re-login."""
        session = _session()
        session._credentials = AuxCredentials.email("user@example.com", "secret")
        calls = []

        async def request_once(*args, **kwargs):
            endpoint = kwargs["endpoint"]
            calls.append(endpoint)
            if endpoint == "account/login":
                return {"status": 0, "loginsession": "new-session", "userid": "user"}
            if calls.count("appsync/group/member/getfamilylist") == 1:
                raise AuxSessionExpired(code=-1000, endpoint=endpoint)
            return {"status": 0, "data": {"ok": True}}

        session._request_once = AsyncMock(side_effect=request_once)

        result = await session.make_request("appsync/group/member/getfamilylist")

        assert result == {"status": 0, "data": {"ok": True}}
        assert session.loginsession == "new-session"
        assert calls == [
            "appsync/group/member/getfamilylist",
            "account/login",
            "appsync/group/member/getfamilylist",
        ]

    async def test_session_recovery_bad_credentials_raises_auth_error(self):
        """Test failed silent re-login surfaces an auth-specific error."""
        session = _session()
        session._credentials = AuxCredentials.email("user@example.com", "secret")

        async def request_once(*args, **kwargs):
            endpoint = kwargs["endpoint"]
            if endpoint == "account/login":
                return {"status": -1006}
            raise AuxSessionExpired(code=-1000, endpoint=endpoint)

        session._request_once = AsyncMock(side_effect=request_once)

        with pytest.raises(AuxAuthError):
            await session.make_request("device/query")


def test_retry_after_is_clamped():
    """Test cloud backoff cannot cause a busy loop or multi-hour stall."""
    assert parse_retry_after("0") == 1
    assert parse_retry_after("120") == 120
    assert parse_retry_after("99999") == 3600
    assert parse_retry_after("not-a-date") is None


async def test_http_transport_uses_timeout_and_default_tls_verification():
    """Test HTTP requests set explicit timeouts and never disable TLS."""
    response = MagicMock(status=200, headers={})
    response.text = AsyncMock(return_value='{"status": 0}')
    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=response)
    context_manager.__aexit__ = AsyncMock(return_value=False)
    client = MagicMock()
    client.request.return_value = context_manager

    session = AuxCloudSession(region="eu", session=client)
    await session._request_once(
        url="https://example.com/test",
        endpoint="test",
        headers={},
        data=None,
        data_raw=None,
        params=None,
    )

    request_kwargs = client.request.call_args.kwargs
    assert request_kwargs["timeout"] is REQUEST_TIMEOUT
    assert "ssl" not in request_kwargs


async def test_session_recovery_is_single_flight():
    """Test concurrent expired requests share one replacement login."""
    session = AuxCloudSession(region="eu", session=MagicMock(closed=False))
    session._credentials = AuxCredentials.email("user@example.com", "secret")
    session.loginsession = "expired"
    session.userid = "user"

    async def login_once(*args, **kwargs):
        await asyncio.sleep(0)
        session.loginsession = "fresh"
        session.userid = "user"
        return None

    session._login_unlocked = AsyncMock(side_effect=login_once)

    assert await asyncio.gather(
        session.recover_session(expired_session="expired"),
        session.recover_session(expired_session="expired"),
    ) == [None, None]
    session._login_unlocked.assert_awaited_once()


async def test_reauthenticated_retry_builds_fresh_headers():
    """Test a recovered request never reuses the expired authentication headers."""
    session = AuxCloudSession(region="eu", session=MagicMock(closed=False))
    session.loginsession = "expired"
    session.userid = "old-user"
    headers: list[dict[str, str]] = []

    async def request_once(**kwargs):
        headers.append(kwargs["headers"])
        if len(headers) == 1:
            raise AuxSessionExpired(code=-1000)
        return {"status": 0}

    async def recover_session(*, expired_session):
        assert expired_session == "expired"
        session.loginsession = "fresh"
        session.userid = "new-user"

    session._request_once = AsyncMock(side_effect=request_once)
    session.recover_session = AsyncMock(side_effect=recover_session)

    assert await session.make_request("device/query") == {"status": 0}
    assert [header["loginsession"] for header in headers] == ["expired", "fresh"]
    assert headers[1]["userid"] == "new-user"
