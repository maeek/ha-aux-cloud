"""AUX Cloud coordinator."""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
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
    issue_id_for_error,
)
from .const import _LOGGER, DOMAIN, MAX_FAILED_POLLS
from .util import DeviceStateHelper, deduplicate_devices_by_endpoint_id

FALLBACK_SCAN_INTERVAL = timedelta(minutes=5)
WEBSOCKET_SETUP_RETRY_INITIAL_DELAY = 5
WEBSOCKET_SETUP_RETRY_MAX_DELAY = 60
REPAIR_ISSUE_IDS = {"api_unavailable", "auth_failed", "rate_limited"}


class AuxCloudCoordinator(
    DataUpdateCoordinator
):  # pylint: disable=too-many-instance-attributes
    """DataUpdateCoordinator for AUX Cloud."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        hass: HomeAssistant,
        api: AuxCloudAPI,
        email: str | None,
        password: str,
        selected_device_ids: list,
        *,
        phone_number: str | None = None,
    ):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="AUX Cloud Coordinator",
            update_interval=None,
        )
        self.api = api
        self.email = email
        self.phone_number = phone_number
        self.password = password
        self.selected_device_ids = selected_device_ids
        self.devices = []
        self._device_state_helpers: dict[str, DeviceStateHelper] = {}
        self._websocket_task: asyncio.Task | None = None
        self._websocket_degraded = False
        self._active_issue_ids: set[str] = set()

    async def async_start_websocket(self):
        """Start websocket updates for selected devices."""
        if self._websocket_task is not None and not self._websocket_task.done():
            return

        self._websocket_task = asyncio.create_task(
            self._async_run_websocket(),
            name="aux_cloud_websocket_runner",
        )

    async def _async_run_websocket(self):
        """Run websocket updates until the config entry unloads."""
        retry_delay = WEBSOCKET_SETUP_RETRY_INITIAL_DELAY
        try:
            while True:
                try:
                    await self.api.async_run_websocket(
                        devices=self.devices,
                        listener=self._async_handle_websocket_message,
                        state_listener=self._async_handle_websocket_state,
                    )
                    _LOGGER.debug("AUX Cloud websocket runner returned unexpectedly")
                except Exception as exc:  # pylint: disable=broad-except
                    _LOGGER.debug("AUX Cloud websocket setup retrying: %s", exc)
                await self._async_handle_websocket_state(AuxWebSocketState.DEGRADED)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, WEBSOCKET_SETUP_RETRY_MAX_DELAY)
        finally:
            if self._websocket_task is asyncio.current_task():
                self._websocket_task = None

    async def _async_handle_websocket_state(self, state: AuxWebSocketState):
        """Handle websocket health changes."""
        if state is AuxWebSocketState.READY:
            if self._websocket_degraded:
                _LOGGER.info("AUX Cloud websocket restored; disabling HTTP fallback")
            self._websocket_degraded = False
            self.update_interval = None
            return

        if state is not AuxWebSocketState.DEGRADED:
            return

        if not self._websocket_degraded:
            _LOGGER.warning(
                "AUX Cloud websocket unavailable; enabling %s HTTP fallback",
                FALLBACK_SCAN_INTERVAL,
            )
            self._websocket_degraded = True
            self.update_interval = FALLBACK_SCAN_INTERVAL
            self.hass.async_create_task(self.async_request_refresh())
            return

        if self.update_interval is None:
            self.update_interval = FALLBACK_SCAN_INTERVAL

    async def async_close(self):
        """Close coordinator resources."""
        if self._websocket_task and not self._websocket_task.done():
            self._websocket_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._websocket_task
        self._websocket_task = None
        await self.api.close_websocket()

    def get_device_by_endpoint_id(self, endpoint_id: str):
        """Get a device by its endpoint ID."""
        data = self.data or {"devices": self.devices}
        return next(
            (
                device
                for device in data.get("devices", [])
                if device.get("endpointId") == endpoint_id
            ),
            None,
        )

    def get_state_helper(
        self, endpoint_id: str, initial_params: dict
    ) -> DeviceStateHelper:
        """Get or create a shared state helper for a single physical device."""
        helper = self._device_state_helpers.get(endpoint_id)
        if helper is None:
            helper = DeviceStateHelper(initial_params, MAX_FAILED_POLLS)
            self._device_state_helpers[endpoint_id] = helper
        return helper

    async def async_set_device_params(self, device: dict, params: dict):
        """Set device params and merge the confirmed response into coordinator data."""
        confirmed_params = await self.api.set_device_params(device, params)
        self._merge_device_params(device["endpointId"], confirmed_params or params)

    async def _async_handle_websocket_message(self, message: dict):
        """Handle a websocket update message."""
        updates = extract_websocket_updates(message)
        if not updates:
            return

        changed = False
        for update in updates:
            if update.get("available") is False:
                changed = self._mark_device_unavailable(update["endpointId"]) or changed
                continue
            changed = (
                self._merge_device_params(
                    update["endpointId"],
                    update["params"],
                    available=update.get("available"),
                )
                or changed
            )

        if changed:
            _LOGGER.debug("Merged %d AUX Cloud websocket update(s)", len(updates))

    def _mark_device_unavailable(self, endpoint_id: str) -> bool:
        """Mark a device unavailable from an explicit websocket offline update."""
        device = self.get_device_by_endpoint_id(endpoint_id)
        if device is None:
            return False

        device_name = device.get("friendlyName", endpoint_id)
        helper = self._device_state_helpers.get(endpoint_id)
        helper_changed = (
            helper.mark_unavailable(device_name) if helper is not None else False
        )
        changed = bool(device.get("params")) or device.get("state") != 0 or helper_changed
        device["state"] = 0
        device["params"] = {}
        device["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        if changed:
            self.async_set_updated_data({"devices": self.devices})
        return changed

    def _merge_device_params(
        self,
        endpoint_id: str,
        params: dict,
        *,
        available: bool | None = None,
    ) -> bool:
        """Merge params into a device and notify entities."""
        device = self.get_device_by_endpoint_id(endpoint_id)
        if device is None or not params:
            return False

        cleaned_params = {
            key: value for key, value in params.items() if key not in {"did", "pid"}
        }
        if not cleaned_params:
            return False

        if available is True:
            device["state"] = 1
        device.setdefault("params", {}).update(cleaned_params)
        device["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.api.normalize_device_params(device)
        self.async_set_updated_data({"devices": self.devices})
        return True

    async def _async_update_data(self):
        """Fetch data from AUX Cloud."""
        _LOGGER.debug("Updating AUX Cloud data...")

        try:
            if not self.api.is_logged_in():
                _LOGGER.debug("Logging into AUX Cloud API...")
                if self.phone_number:
                    login_success = await self.api.login(
                        password=self.password,
                        phone_number=self.phone_number,
                    )
                else:
                    login_success = await self.api.login(self.email, self.password)
                if not login_success:
                    raise AuxAuthError("Login to AUX Cloud API failed")

            if self.api.families is None:
                _LOGGER.debug("Fetching families from AUX Cloud API...")
                await self.api.get_families()

            device_tasks = []
            for family_id in self.api.families:
                device_tasks.append(
                    self.api.get_devices(
                        family_id,
                        shared=False,
                        selected_devices=self.selected_device_ids,
                    )
                )
                device_tasks.append(
                    self.api.get_devices(
                        family_id,
                        shared=True,
                        selected_devices=self.selected_device_ids,
                    )
                )

            devices_results = await asyncio.gather(
                *device_tasks, return_exceptions=True
            )
            all_devices = self._collect_device_results(devices_results)

            self.devices = all_devices
            _LOGGER.debug("Fetched AUX Cloud data: %s devices", len(self.devices))

            current_endpoint_ids = {
                device["endpointId"]
                for device in self.devices
                if "endpointId" in device
            }
            stale_helpers = set(self._device_state_helpers) - current_endpoint_ids
            for endpoint_id in stale_helpers:
                self._device_state_helpers.pop(endpoint_id, None)

            self._async_clear_cloud_issues()
            return {"devices": self.devices}

        except (AuxAuthError, AuxSessionExpired) as exc:
            self._async_create_cloud_issue(exc)
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except (AuxNetworkError, AuxServerError, AuxRateLimitError) as exc:
            self._async_create_cloud_issue(exc)
            raise UpdateFailed(str(exc)) from exc
        except Exception as exc:
            raise UpdateFailed(f"Error updating AUX Cloud data: {exc}") from exc

    def _collect_device_results(self, devices_results: list) -> list[dict]:
        """Collect device-list query results, preserving partial success."""
        all_devices = []
        query_errors = []

        for result in devices_results:
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                query_errors.append(result)
                _LOGGER.warning("Skipping failed AUX Cloud device query: %s", result)
                continue

            for device in result:
                if isinstance(device, BaseException):
                    if not isinstance(device, Exception):
                        raise device
                    query_errors.append(device)
                    _LOGGER.warning(
                        "Skipping failed AUX Cloud device entry: %s", device
                    )
                    continue
                if (
                    device["endpointId"] in self.selected_device_ids
                    or not self.selected_device_ids
                ):
                    all_devices.append(device)

        if not all_devices and query_errors:
            raise _preferred_query_error(query_errors)
        return deduplicate_devices_by_endpoint_id(all_devices)

    def _async_create_cloud_issue(self, error: AuxApiError) -> None:
        """Create or update the Repairs issue for a cloud API error."""
        issue_id = issue_id_for_error(error)
        severity = (
            ir.IssueSeverity.ERROR
            if issue_id == "auth_failed"
            else ir.IssueSeverity.WARNING
        )
        if issue_id not in self._active_issue_ids:
            _LOGGER.warning("AUX Cloud issue detected: %s", error)
        self._active_issue_ids.add(issue_id)
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=severity,
            translation_key=issue_id,
            translation_placeholders={"error": str(error)},
        )

    def _async_clear_cloud_issues(self) -> None:
        """Clear cloud API Repairs issues after a successful refresh."""
        if self._active_issue_ids:
            _LOGGER.info("AUX Cloud API communication restored")
        for issue_id in REPAIR_ISSUE_IDS:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        self._active_issue_ids.clear()


def _preferred_query_error(errors: list[BaseException]) -> BaseException:
    """Return the most useful error to surface for a fully failed refresh."""
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
