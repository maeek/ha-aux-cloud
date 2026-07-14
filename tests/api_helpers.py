"""Shared API test builders and repository fakes."""

import base64
import json


def mock_device() -> dict:
    """Return a minimal mock device for command tests."""
    return {
        "endpointId": "device1",
        "friendlyName": "AC Unit 1",
        "productId": "000000000000000000000000c0620000",
        "devSession": "dev-session",
        "devicetypeFlag": 1,
        "mac": "aa:bb:cc:dd:ee:ff",
        "cookie": mock_cookie(),
        "familyId": "family1",
    }


def mock_cookie(**metadata: object) -> str:
    """Return a base64 AUX cookie with optional non-secret metadata."""
    payload = {"terminalid": 1234, "aeskey": "key", **metadata}
    return base64.b64encode(json.dumps(payload).encode()).decode()


def mock_heat_pump(ver: int = 3) -> dict:
    """Return a minimal mock heat-pump device."""
    device = mock_device()
    device["productId"] = "000000000000000000000000c3aa0000"
    device["friendlyName"] = "Heat Pump"
    device["extern"] = json.dumps({"ver": ver})
    return device


class FakeRepositorySession:
    """Fake session for repository bootstrap tests."""

    userid = "user"

    def __init__(self, device: dict, *, online: bool = True) -> None:
        self._device = device
        self._online = online

    def get_headers(self, **kwargs: str) -> dict[str, str]:
        """Return passed headers."""
        return kwargs

    async def make_request(self, **kwargs: object) -> dict:
        """Return canned repository responses."""
        endpoint = kwargs["endpoint"]
        if isinstance(endpoint, str) and "dev/query" in endpoint:
            return {"status": 0, "data": {"endpoints": [self._device]}}
        if endpoint == "device/control/v2/querystate":
            return {
                "event": {
                    "payload": {
                        "status": 0,
                        "data": [{"did": "device1", "state": int(self._online)}],
                    }
                }
            }
        raise AssertionError(endpoint)


class FakeInitialParamsControl:
    """Fake control service for initial parameter query tests."""

    def __init__(self, query_results: dict[tuple[str, ...], dict | Exception]) -> None:
        self._query_results = query_results
        self.queries: list[list[str]] = []

    async def get_device_params(
        self, _queried_device: dict, params: list[str] | None = None
    ) -> dict:
        """Return or raise the result configured for a query."""
        self.queries.append(list(params or []))
        result = self._query_results[tuple(params or [])]
        if isinstance(result, Exception):
            raise result
        return result
