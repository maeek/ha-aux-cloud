"""AUX Cloud coordinator."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AuxApiError,
    AuxAuthError,
    AuxCloudAPI,
    AuxNetworkError,
    AuxRateLimitError,
    AuxServerError,
    AuxSessionExpired,
    AuxWebSocketState,
    extract_websocket_updates,
)
from .const import _LOGGER, MAX_FAILED_POLLS, TOPOLOGY_SCAN_INTERVAL_MINUTES
from .models import AuxDevice, CoordinatorData
from .util import (
    DeviceStateHelper,
    deduplicate_devices_by_endpoint_id,
    device_identifier,
)

FALLBACK_SCAN_INTERVAL = timedelta(minutes=5)
TOPOLOGY_SCAN_INTERVAL = timedelta(minutes=TOPOLOGY_SCAN_INTERVAL_MINUTES)
WEBSOCKET_SETUP_RETRY_INITIAL_DELAY = 5
WEBSOCKET_SETUP_RETRY_MAX_DELAY = 60

DeviceListener = Callable[[list[AuxDevice]], None]


class AuxCloudCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Own AUX Cloud inventory, push state, and command transactions."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: AuxCloudAPI,
        email: str | None,
        password: str,
        *,
        config_entry: ConfigEntry | None = None,
        phone_number: str | None = None,
    ) -> None:
        """Initialize the coordinator."""
        coordinator_kwargs = {
            "name": "AUX Cloud",
            "update_interval": TOPOLOGY_SCAN_INTERVAL,
            "always_update": False,
        }
        if (
            config_entry is not None
            and "config_entry"
            in inspect.signature(DataUpdateCoordinator.__init__).parameters
        ):
            coordinator_kwargs["config_entry"] = config_entry
        super().__init__(hass, _LOGGER, **coordinator_kwargs)
        self.api = api
        self._aux_config_entry = config_entry
        self._entity_config_entry_id = config_entry.entry_id if config_entry else None
        self._entity_unique_id_salt = (
            (config_entry.unique_id or config_entry.entry_id) if config_entry else ""
        )
        self.email = email
        self.phone_number = phone_number
        self.password = password
        self.devices: list[AuxDevice] = []
        self._device_state_helpers: dict[str, DeviceStateHelper] = {}
        self._command_locks: dict[str, asyncio.Lock] = {}
        self._reserved_entity_unique_ids: set[tuple[str, str]] = set()
        self._device_listeners: set[DeviceListener] = set()
        self._missing_complete_scans: dict[str, int] = {}
        self._update_generation = 0
        self._websocket_task: asyncio.Task[None] | None = None
        self._websocket_degraded = False
        self._cloud_failure_logged = False

    @callback
    def async_add_device_listener(self, listener: DeviceListener) -> Callable[[], None]:
        """Register a listener that receives newly discovered devices."""
        self._device_listeners.add(listener)

        @callback
        def remove_listener() -> None:
            self._device_listeners.discard(listener)

        return remove_listener

    async def async_start_websocket(self) -> None:
        """Start the supervised websocket update task."""
        if self._websocket_task is not None and not self._websocket_task.done():
            return
        self._websocket_task = self.hass.async_create_task(
            self._async_run_websocket(),
            "aux_cloud_websocket_runner",
        )

    async def _async_run_websocket(self) -> None:
        """Run websocket updates until the config entry unloads."""
        retry_delay = WEBSOCKET_SETUP_RETRY_INITIAL_DELAY
        try:
            while True:
                try:
                    await self.api.async_run_websocket(
                        devices=cast(list[dict], self.devices),
                        listener=self._async_handle_websocket_message,
                        state_listener=self._async_handle_websocket_state,
                    )
                except asyncio.CancelledError:
                    raise
                except (AuxApiError, ConnectionError, TimeoutError) as exc:
                    _LOGGER.debug(
                        "AUX websocket runner restarting (%s)", type(exc).__name__
                    )
                except Exception as exc:  # Protect HA from third-party relay faults.
                    _LOGGER.debug(
                        "Unexpected AUX websocket failure (%s)", type(exc).__name__
                    )
                await self._async_handle_websocket_state(AuxWebSocketState.DEGRADED)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, WEBSOCKET_SETUP_RETRY_MAX_DELAY)
        finally:
            if self._websocket_task is asyncio.current_task():
                self._websocket_task = None

    async def _async_handle_websocket_state(self, state: AuxWebSocketState) -> None:
        """Adjust fallback polling according to websocket health."""
        if state is AuxWebSocketState.READY:
            if self._websocket_degraded:
                _LOGGER.info("AUX Cloud websocket restored")
            self._websocket_degraded = False
            self.update_interval = TOPOLOGY_SCAN_INTERVAL
            return
        if state is not AuxWebSocketState.DEGRADED:
            return
        if not self._websocket_degraded:
            _LOGGER.warning(
                "AUX Cloud websocket unavailable; enabling fallback polling"
            )
            self._websocket_degraded = True
            self.update_interval = FALLBACK_SCAN_INTERVAL
            self.hass.async_create_task(self.async_request_refresh())

    async def async_close(self) -> None:
        """Close coordinator resources."""
        if self._websocket_task and not self._websocket_task.done():
            self._websocket_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._websocket_task
        self._websocket_task = None
        await self.api.close_websocket()

    def get_device_by_endpoint_id(self, endpoint_id: str) -> AuxDevice | None:
        """Return a device by its raw cloud endpoint ID."""
        return next(
            (
                device
                for device in (self.data or {"devices": self.devices})["devices"]
                if device.get("endpointId") == endpoint_id
            ),
            None,
        )

    def get_state_helper(
        self, endpoint_id: str, initial_params: dict[str, Any]
    ) -> DeviceStateHelper:
        """Return the shared state helper for one physical device."""
        return self._device_state_helpers.setdefault(
            endpoint_id,
            DeviceStateHelper(initial_params, MAX_FAILED_POLLS),
        )

    @property
    def update_generation(self) -> int:
        """Return a monotonic identifier for entity cache synchronization."""
        return self._update_generation

    @property
    def websocket_degraded(self) -> bool:
        """Return whether HTTP fallback polling is currently active."""
        return self._websocket_degraded

    async def async_set_device_params(
        self, device: AuxDevice, params: dict[str, Any]
    ) -> None:
        """Serialize and publish one optimistic device command transaction."""
        endpoint_id = device["endpointId"]
        async with self._command_locks.setdefault(endpoint_id, asyncio.Lock()):
            current = self.get_device_by_endpoint_id(endpoint_id)
            if current is None:
                raise AuxApiError("AUX Cloud device is no longer available")
            if not self.devices and self.data:
                self.devices = list(self.data["devices"])
            previous = dict(current.get("params", {}))
            self._replace_device_params(endpoint_id, {**previous, **params})
            self._publish_devices()
            try:
                confirmed = await self.api.set_device_params(
                    cast(dict, current), params
                )
            except Exception:
                self._replace_device_params(endpoint_id, previous)
                if helper := self._device_state_helpers.get(endpoint_id):
                    helper.replace_params(previous)
                self._publish_devices()
                raise
            self._replace_device_params(
                endpoint_id,
                {**previous, **(confirmed or params)},
            )
            self._publish_devices()

    async def _async_handle_websocket_message(self, message: dict[str, Any]) -> None:
        """Merge all updates from one websocket frame in one coordinator write."""
        updates = extract_websocket_updates(message)
        if not updates:
            return
        self.devices = [
            {**device, "params": dict(device.get("params", {}))}
            for device in self.devices
        ]
        changed = False
        for update in updates:
            endpoint_id = update["endpointId"]
            if update.get("available") is False:
                changed = self._mark_device_unavailable(endpoint_id) or changed
            else:
                changed = (
                    self._merge_device_params(
                        endpoint_id,
                        update["params"],
                        available=update.get("available"),
                    )
                    or changed
                )
        if changed:
            self._publish_devices()

    def _mark_device_unavailable(self, endpoint_id: str) -> bool:
        """Mark a device unavailable after an explicit cloud offline event."""
        device = next(
            (item for item in self.devices if item.get("endpointId") == endpoint_id),
            None,
        )
        if device is None:
            return False
        helper = self._device_state_helpers.get(endpoint_id)
        helper_changed = helper.mark_unavailable("AUX device") if helper else False
        changed = (
            bool(device.get("params")) or device.get("state") != 0 or helper_changed
        )
        device["state"] = 0
        device["params"] = {}
        device["last_updated"] = _timestamp()
        return changed

    def _merge_device_params(
        self,
        endpoint_id: str,
        params: dict[str, Any],
        *,
        available: bool | None = None,
    ) -> bool:
        """Merge pushed parameters into the current copy-on-write snapshot."""
        device = next(
            (item for item in self.devices if item.get("endpointId") == endpoint_id),
            None,
        )
        if device is None:
            return False
        cleaned = {
            key: value for key, value in params.items() if key not in {"did", "pid"}
        }
        if not cleaned and available is not True:
            return False
        if available is True:
            device["state"] = 1
        device["params"] = {**device.get("params", {}), **cleaned}
        device["last_updated"] = _timestamp()
        self.api.normalize_device_params(cast(dict, device))
        return True

    def _replace_device_params(self, endpoint_id: str, params: dict[str, Any]) -> None:
        """Replace one device parameter mapping without mutating published data."""
        updated_devices: list[AuxDevice] = []
        for device in self.devices:
            if device.get("endpointId") != endpoint_id:
                updated_devices.append(device)
                continue
            updated_device: AuxDevice = {
                **device,
                "params": dict(params),
                "last_updated": _timestamp(),
            }
            self.api.normalize_device_params(cast(dict, updated_device))
            updated_devices.append(updated_device)
        self.devices = updated_devices

    def _publish_devices(self) -> None:
        """Publish the current inventory as a new coordinator snapshot."""
        self._update_generation += 1
        self.async_set_updated_data({"devices": list(self.devices)})

    async def _async_update_data(self) -> CoordinatorData:
        """Run an authoritative account topology and state scan."""
        try:
            await self._async_ensure_login()
            await self.api.get_families()
            family_ids = list((self.api.families or {}).keys())
            tasks = [
                self.api.get_devices(family_id, shared=shared)
                for family_id in family_ids
                for shared in (False, True)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            discovered, complete = self._collect_device_results(results)
            previous_ids = {
                device["endpointId"]
                for device in self.devices
                if device.get("endpointId")
            }
            self.devices = self._reconcile_inventory(discovered, complete=complete)
            current_ids = {
                device["endpointId"]
                for device in self.devices
                if device.get("endpointId")
            }
            new_ids = current_ids - previous_ids
            removed_ids = previous_ids - current_ids
            for endpoint_id in removed_ids:
                self._device_state_helpers.pop(endpoint_id, None)
                self._command_locks.pop(endpoint_id, None)
            self._async_remove_stale_devices(removed_ids)

            if self._cloud_failure_logged:
                _LOGGER.info("AUX Cloud communication restored")
            self._cloud_failure_logged = False
            if new_ids:
                new_devices = [
                    device
                    for device in self.devices
                    if device.get("endpointId") in new_ids
                ]
                for listener in tuple(self._device_listeners):
                    listener(new_devices)
            if new_ids or removed_ids:
                self.hass.async_create_task(self._async_refresh_websocket_membership())
            self._update_generation += 1
            return {"devices": list(self.devices)}
        except (AuxAuthError, AuxSessionExpired) as exc:
            raise ConfigEntryAuthFailed(
                "AUX Cloud credentials must be updated"
            ) from exc
        except AuxRateLimitError as exc:
            self._log_cloud_failure_once(exc)
            if exc.retry_after is not None:
                raise UpdateFailed(str(exc), retry_after=exc.retry_after) from exc
            raise UpdateFailed(str(exc)) from exc
        except (AuxNetworkError, AuxServerError) as exc:
            self._log_cloud_failure_once(exc)
            raise UpdateFailed(str(exc)) from exc
        except AuxApiError as exc:
            raise UpdateFailed(str(exc)) from exc
        except Exception as exc:
            raise UpdateFailed("Unexpected AUX Cloud update failure") from exc

    async def _async_ensure_login(self) -> None:
        """Authenticate when the shared API session has no active identity."""
        if self.api.is_logged_in():
            return
        if self.phone_number:
            success = await self.api.login(
                password=self.password,
                phone_number=self.phone_number,
            )
        else:
            success = await self.api.login(self.email, self.password)
        if not success:
            raise AuxAuthError("Login to AUX Cloud failed")

    def _collect_device_results(
        self, results: list[Any]
    ) -> tuple[list[AuxDevice], bool]:
        """Collect query results and report whether every query completed."""
        devices: list[AuxDevice] = []
        errors: list[BaseException] = []
        for result in results:
            if isinstance(result, BaseException):
                if isinstance(result, asyncio.CancelledError):
                    raise result
                errors.append(result)
                continue
            for device in result:
                if isinstance(device, BaseException):
                    errors.append(device)
                else:
                    devices.append(device)
        if not devices and errors:
            raise _preferred_query_error(errors)
        return (
            cast(
                list[AuxDevice],
                deduplicate_devices_by_endpoint_id(cast(list[dict], devices)),
            ),
            not errors,
        )

    def _reconcile_inventory(
        self, discovered: list[AuxDevice], *, complete: bool
    ) -> list[AuxDevice]:
        """Avoid destructive removals on partial or one-off empty scans."""
        discovered_by_id = {
            device["endpointId"]: device
            for device in discovered
            if device.get("endpointId")
        }
        previous_by_id = {
            device["endpointId"]: device
            for device in self.devices
            if device.get("endpointId")
        }
        if not complete:
            return list(discovered_by_id.values()) + [
                device
                for endpoint_id, device in previous_by_id.items()
                if endpoint_id not in discovered_by_id
            ]

        retained = list(discovered_by_id.values())
        for endpoint_id, old_device in previous_by_id.items():
            if endpoint_id in discovered_by_id:
                self._missing_complete_scans.pop(endpoint_id, None)
                continue
            missing_count = self._missing_complete_scans.get(endpoint_id, 0) + 1
            self._missing_complete_scans[endpoint_id] = missing_count
            if missing_count < 2:
                retained.append(old_device)
        return retained

    async def _async_refresh_websocket_membership(self) -> None:
        """Reset relay subscriptions after inventory membership changes."""
        websocket = self.api.ws_api
        subscribe = getattr(websocket, "subscribe_devices", None)
        if (
            websocket is None
            or not websocket.connected
            or not inspect.iscoroutinefunction(subscribe)
        ):
            return
        try:
            await websocket.subscribe_devices(
                cast(list[dict], self.devices), reset=True
            )
        except (ConnectionError, TimeoutError, AuxApiError):
            await self.api.close_websocket()

    @callback
    def _async_remove_stale_devices(self, endpoint_ids: set[str]) -> None:
        """Remove devices confirmed absent from two complete inventory scans."""
        if not endpoint_ids or self._aux_config_entry is None:
            return
        registry = dr.async_get(self.hass)
        for endpoint_id in endpoint_ids:
            device = registry.async_get_device(
                identifiers={device_identifier(endpoint_id)}
            )
            if device is not None:
                registry.async_update_device(
                    device_id=device.id,
                    remove_config_entry_id=self._aux_config_entry.entry_id,
                )

    def _log_cloud_failure_once(self, error: BaseException) -> None:
        """Log a transient cloud outage once until a successful scan."""
        if self.data is None or self._cloud_failure_logged:
            return
        self._cloud_failure_logged = True
        _LOGGER.warning("AUX Cloud update unavailable (%s)", type(error).__name__)


def _timestamp() -> str:
    """Return a display-only timestamp for diagnostics."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _preferred_query_error(errors: list[BaseException]) -> BaseException:
    """Return the most useful error from a fully failed inventory scan."""
    for error_type in (
        AuxAuthError,
        AuxSessionExpired,
        AuxRateLimitError,
        AuxServerError,
        AuxNetworkError,
        AuxApiError,
    ):
        for error in errors:
            if isinstance(error, error_type):
                return error
    return errors[0]
