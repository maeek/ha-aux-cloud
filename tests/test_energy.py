"""AUX energy statistics parsing, fetching, publication, and sensors."""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.aux_cloud.sensor as sensor_platform
from custom_components.aux_cloud.api.errors import AuxServerError
from custom_components.aux_cloud.api.models import (
    EnergyReading,
    EnergyStatistics,
    InventorySnapshot,
)
from custom_components.aux_cloud.const import DOMAIN
from custom_components.aux_cloud.coordinator import AuxCloudCoordinator
from custom_components.aux_cloud.dna import DnaClient
from custom_components.aux_cloud.dna.codec import (
    ENERGY_STATISTICS_ENDPOINT,
    build_energy_statistics_request,
    parse_energy_statistics_page,
)
from custom_components.aux_cloud.sensor import AuxCloudSensor, AuxEnergySensor

from .api_helpers import mock_device, mock_heat_pump

pytest_plugins = "pytest_homeassistant_custom_component"


def _row(day: str, value: object) -> dict:
    return {"did": "device1", "occurtime": f"{day}_00:00:00", "tenelec": value}


def _page(rows: list[dict], total: int | None = None) -> dict:
    return {
        "status": 0,
        "msg": "ok",
        "table": [
            {
                "did": "device1",
                "total": len(rows) if total is None else total,
                "cnt": len(rows),
                "values": rows,
            }
        ],
    }


def test_energy_request_and_page_parsing():
    """Report queries mirror the app and pages keep only usable daily rows."""
    request = build_energy_statistics_request(
        mock_device(), "fw_auxoverseamonthconsum_v1", offset=40
    )
    assert request["report"] == "fw_auxoverseamonthconsum_v1"
    assert request["device"][0]["did"] == "device1"
    assert request["device"][0]["offset"] == 40
    assert request["device"][0]["start"] < request["device"][0]["end"]

    page = _page(
        [
            _row("2026-10-14", 1.0625),
            _row("2026-10-15", 3),
            _row("2026-10-16", True),
            _row("not-a-day", 0.5),
            {"did": "device1", "occurtime": "2026-10-17_00:00:00"},
            "garbage",
        ],
        total=83,
    )
    page["table"].append(
        {"did": "other", "total": 1, "values": [_row("2026-01-01", 9)]}
    )
    readings, total = parse_energy_statistics_page(page, endpoint_id="device1")

    assert total == 83
    assert readings == [
        EnergyReading(date(2026, 10, 14), 1.0625),
        EnergyReading(date(2026, 10, 15), 3.0),
    ]
    with pytest.raises(AuxServerError):
        parse_energy_statistics_page({"status": 0}, endpoint_id="device1")


async def test_client_pages_through_history_and_selects_regional_report():
    """The client follows the row total across pages and uses the CN report there."""
    requests: list[dict] = []
    pages = [
        _page([_row("2026-10-13", 0.125), _row("2026-10-14", 1.0625)], total=3),
        _page([_row("2026-10-15", 3.0625)], total=3),
    ]

    async def make_request(endpoint, *, data, **_kwargs):
        assert endpoint == ENERGY_STATISTICS_ENDPOINT
        requests.append(data)
        return pages.pop(0)

    client = DnaClient(region="cn", session=MagicMock(closed=False))
    client._session.make_request = make_request

    statistics = await client.get_energy_statistics(mock_device())

    assert [request["report"] for request in requests] == ["serv_auxmonthelec_v1"] * 2
    assert [request["device"][0]["offset"] for request in requests] == [0, 2]
    assert statistics.endpoint_id == "device1"
    assert statistics.total_kwh == pytest.approx(4.25)
    assert statistics.energy_for_day(date(2026, 10, 15)) == pytest.approx(3.0625)


async def test_coordinator_refreshes_energy_only_for_reporting_air_conditioners(hass):
    """Energy failures and silent products never disturb the inventory scan."""
    air_conditioner = {**mock_device(), "state": 1, "params": {"pwr": 1}}
    heat_pump = {
        **mock_heat_pump(),
        "endpointId": "hp1",
        "state": 1,
        "params": {"hp_pwr": 1},
    }
    api = MagicMock()
    api.is_logged_in.return_value = True
    api.scan_devices = AsyncMock(
        return_value=InventorySnapshot((air_conditioner, heat_pump), complete=True)
    )
    api.update_realtime_devices = AsyncMock()
    reported = EnergyStatistics("device1", (EnergyReading(date(2026, 10, 15), 2.5),))
    api.get_energy_statistics = AsyncMock(return_value=reported)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
    )
    entry.add_to_hass(hass)
    coordinator = AuxCloudCoordinator(hass, api, config_entry=entry)

    assert set(await coordinator._async_update_data()) == {"device1", "hp1"}
    api.get_energy_statistics.assert_awaited_once()
    assert api.get_energy_statistics.await_args.args[0]["endpointId"] == "device1"
    assert coordinator.get_energy_statistics("device1") is reported
    assert coordinator.get_energy_statistics("hp1") is None

    api.get_energy_statistics = AsyncMock(return_value=EnergyStatistics("device1", ()))
    await coordinator._async_update_data()
    assert coordinator.get_energy_statistics("device1") is reported

    api.get_energy_statistics = AsyncMock(side_effect=AuxServerError("stats down"))
    await coordinator._async_update_data()
    assert coordinator.get_energy_statistics("device1") is reported

    # Inventory drops a device only after two complete scans without it.
    api.scan_devices.return_value = InventorySnapshot((heat_pump,), complete=True)
    await coordinator._async_update_data()
    assert coordinator.get_energy_statistics("device1") is reported
    await coordinator._async_update_data()
    assert coordinator.get_energy_statistics("device1") is None


async def test_energy_sensors_appear_once_history_exists(hass):
    """Energy sensors are added when history arrives and expose daily totals."""
    api = MagicMock()
    api.close = AsyncMock()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_REGION: "eu",
        },
    )
    entry.add_to_hass(hass)
    coordinator = AuxCloudCoordinator(hass, api, config_entry=entry)
    device = {**mock_device(), "state": 1, "params": {"envtemp": 215}}
    coordinator._state.reconcile(
        [device], complete=True, scan_revision=coordinator._state.revision
    )
    coordinator._publish_devices()
    platform_entry = SimpleNamespace(
        runtime_data=coordinator, async_on_unload=MagicMock()
    )
    added = MagicMock()

    await sensor_platform.async_setup_entry(hass, platform_entry, added)

    assert all(isinstance(entity, AuxCloudSensor) for entity in added.call_args.args[0])
    added.reset_mock()

    today = dt_util.now().date()
    coordinator._energy["device1"] = EnergyStatistics(
        "device1",
        (
            EnergyReading(today - timedelta(days=1), 1.5),
            EnergyReading(today, 0.25),
        ),
    )
    coordinator._publish_devices()

    sensors = {
        entity.entity_description.key: entity for entity in added.call_args.args[0]
    }
    assert set(sensors) == {"energy_total", "energy_today"}
    assert all(isinstance(entity, AuxEnergySensor) for entity in sensors.values())
    assert sensors["energy_total"].available
    assert sensors["energy_total"].native_value == pytest.approx(1.75)
    assert sensors["energy_today"].native_value == pytest.approx(0.25)
    assert sensors["energy_total"].unique_id == "aux_cloud_device1_energy_total"

    coordinator._publish_devices()
    assert added.call_count == 1

    coordinator._energy.clear()
    assert not sensors["energy_total"].available
    assert sensors["energy_today"].native_value is None
