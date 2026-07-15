"""AUX Cloud coordinator."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AuxApiError,
    AuxAuthError,
    AuxCloudClient,
    AuxRateLimitError,
    AuxServerError,
    AuxSessionExpired,
)
from .api.models import AuxCredentials, AuxDevice, DeviceUpdate
from .const import (
    CONF_PHONE_NUMBER,
    DOMAIN,
    TOPOLOGY_SCAN_INTERVAL_MINUTES,
)
from .devices import normalize_device_params
from .identifiers import device_identifier
from .state import (
    AccountState,
    CoordinatorData,
    InventoryDelta,
)

_LOGGER = logging.getLogger(__name__)

FALLBACK_SCAN_INTERVAL = timedelta(minutes=5)
TOPOLOGY_SCAN_INTERVAL = timedelta(minutes=TOPOLOGY_SCAN_INTERVAL_MINUTES)
_API_OUTAGE_NOTIFICATION_ID = f"{DOMAIN}_api_outage"
_API_OUTAGE_NOTIFICATION_TITLE = "AUX/BroadLink Cloud outage"


class AuxCloudCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Own AUX Cloud inventory, push state, and command transactions."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: AuxCloudClient,
        *,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="AUX Cloud",
            update_interval=TOPOLOGY_SCAN_INTERVAL,
            always_update=False,
        )
        self.config_entry: ConfigEntry = config_entry
        self.api = api
        self._state = AccountState(normalize_device_params)
        self._command_locks: dict[str, asyncio.Lock] = {}
        self._reserved_entity_unique_ids: dict[tuple[str, str], str] = {}
        self._websocket_task: asyncio.Task[None] | None = None
        self._websocket_degraded = False
        self._api_outage_reported = False

    @callback
    def start_realtime(self) -> None:
        """Start relay supervision after platforms finish setup."""
        if self._websocket_task is not None and not self._websocket_task.done():
            return
        self._websocket_task = self.config_entry.async_create_background_task(
            self.hass,
            self._run_websocket(),
            "aux_cloud_websocket_runner",
        )

    @callback
    def _set_websocket_connected(self, connected: bool) -> None:
        """Publish relay health transitions and adjust topology polling."""
        degraded = not connected
        if degraded == self._websocket_degraded:
            return
        self._websocket_degraded = degraded
        _LOGGER.info(
            "AUX Cloud websocket %s",
            "unavailable; enabling fallback polling" if degraded else "restored",
        )
        self.update_interval = (
            TOPOLOGY_SCAN_INTERVAL if connected else FALLBACK_SCAN_INTERVAL
        )
        if not connected:
            self.config_entry.async_create_task(
                self.hass,
                self.async_request_refresh(),
                "aux_cloud_fallback_refresh",
            )

    async def async_close(self) -> None:
        """Close coordinator resources."""
        if self._websocket_task is not None and not self._websocket_task.done():
            self._websocket_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._websocket_task
        self._websocket_task = None
        await self.api.close()

    def get_device_by_endpoint_id(self, endpoint_id: str) -> AuxDevice | None:
        """Return a device by its raw cloud endpoint ID."""
        return (self.data or self._state.data).get(endpoint_id)

    @property
    def websocket_degraded(self) -> bool:
        """Return whether HTTP fallback polling is currently active."""
        return self._websocket_degraded

    async def async_set_device_params(
        self, endpoint_id: str, params: dict[str, Any]
    ) -> None:
        """Serialize and publish one optimistic device command transaction."""
        async with self._command_locks.setdefault(endpoint_id, asyncio.Lock()):
            current = self.get_device_by_endpoint_id(endpoint_id)
            if current is None:
                raise AuxApiError("AUX Cloud device is no longer available")
            token = self._state.begin_command(endpoint_id, params)
            if token is None:
                raise AuxApiError("AUX Cloud device is no longer available")
            if token.changed:
                self._publish_devices()
            try:
                await self.api.set_device_params(current, params)
            except (asyncio.CancelledError, Exception):
                if self._state.rollback_command(token):
                    self._publish_devices()
                raise
            # AUX command acknowledgements can contain the snapshot from before
            # the command was applied. Treat success as an acknowledgement of
            # the requested values; later device pushes remain authoritative.
            if self._state.confirm_command(token, params):
                self._publish_devices()

    @callback
    def _handle_websocket_updates(self, updates: tuple[DeviceUpdate, ...]) -> None:
        """Merge one validated relay frame in one coordinator write."""
        if self._state.apply_updates(updates):
            self._publish_devices()

    @callback
    def _publish_devices(self) -> None:
        """Publish push state without postponing the topology scan timer."""
        self.data = self._state.data
        self.last_update_success = True
        self.logger.debug("Manually updated %s data", self.name)
        self.async_update_listeners()

    async def _async_update_data(self) -> CoordinatorData:
        """Run an authoritative account topology and state scan."""
        try:
            data = await self._async_scan_devices()
        except (AuxAuthError, AuxSessionExpired) as exc:
            raise ConfigEntryAuthFailed(
                "AUX Cloud credentials must be updated"
            ) from exc
        except AuxRateLimitError as exc:
            raise UpdateFailed(str(exc), retry_after=exc.retry_after) from exc
        except AuxServerError as exc:
            if exc.http_status is not None and exc.http_status >= 500:
                self._report_api_outage(exc.http_status)
            raise UpdateFailed(str(exc)) from exc
        except AuxApiError as exc:
            raise UpdateFailed(str(exc)) from exc
        persistent_notification.async_dismiss(
            self.hass,
            _API_OUTAGE_NOTIFICATION_ID,
        )
        self._api_outage_reported = False
        return data

    @callback
    def _report_api_outage(self, http_status: int) -> None:
        """Tell the user that a failed refresh is a vendor-cloud outage."""
        if self._api_outage_reported:
            return
        self._api_outage_reported = True
        persistent_notification.async_create(
            self.hass,
            (
                f"The AUX/BroadLink cloud service is returning HTTP {http_status}. "
                "This is an external service outage, not a Home Assistant "
                "configuration problem. The integration will retry automatically and "
                "this notification will disappear when the service recovers. There is "
                "normally no need to remove or reconfigure the integration, or to "
                "report this outage on GitHub."
            ),
            title=_API_OUTAGE_NOTIFICATION_TITLE,
            notification_id=_API_OUTAGE_NOTIFICATION_ID,
        )

    async def _async_scan_devices(self) -> CoordinatorData:
        """Fetch, reconcile, and publish an account inventory snapshot."""
        scan_revision = self._state.revision
        await self._async_ensure_login()
        inventory = await self.api.scan_devices()
        delta = self._state.reconcile(
            inventory.devices,
            complete=inventory.complete,
            scan_revision=scan_revision,
            registry_ids=self._registered_endpoint_ids(),
        )
        self._handle_inventory_changes(delta)
        return self._state.data

    def _handle_inventory_changes(self, delta: InventoryDelta) -> None:
        """Clean up removals and refresh relay membership."""
        for endpoint_id in delta.removed:
            self._command_locks.pop(endpoint_id, None)
            self._reserved_entity_unique_ids = {
                key: owner
                for key, owner in self._reserved_entity_unique_ids.items()
                if owner != endpoint_id
            }
        self._async_remove_stale_devices(set(delta.removed))

        if delta.added or delta.removed:
            self.config_entry.async_create_task(
                self.hass,
                self._async_refresh_websocket_subscriptions(),
                "aux_cloud_websocket_membership",
            )

    async def _async_refresh_websocket_subscriptions(self) -> None:
        """Reset relay membership after account inventory changes."""
        try:
            await self.api.update_realtime_devices(self._state.devices)
        except AuxApiError:
            await self.api.close()

    async def _run_websocket(self) -> None:
        """Reconnect the account relay until the config entry unloads."""
        try:
            await self.api.run_realtime(
                devices=self._state.devices,
                listener=self._handle_websocket_updates,
                connection_listener=self._set_websocket_connected,
            )
        finally:
            if self._websocket_task is asyncio.current_task():
                self._websocket_task = None

    async def _async_ensure_login(self) -> None:
        """Authenticate when the shared API session has no active identity."""
        if self.api.is_logged_in():
            return
        entry_data = self.config_entry.data
        password = entry_data[CONF_PASSWORD]
        if phone_number := entry_data.get(CONF_PHONE_NUMBER):
            credentials = AuxCredentials.phone(phone_number, password)
        else:
            email = entry_data.get(CONF_EMAIL)
            if not email:
                raise AuxAuthError("Missing AUX Cloud account credentials")
            credentials = AuxCredentials.email(email, password)
        await self.api.login(credentials)

    def _registered_endpoint_ids(self) -> set[str]:
        """Return this entry's AUX endpoint IDs from the device registry."""
        registry = dr.async_get(self.hass)
        return {
            identifier[1]
            for device in registry.devices.values()
            if self.config_entry.entry_id in device.config_entries
            for identifier in device.identifiers
            if identifier[0] == DOMAIN
        }

    @callback
    def _async_remove_stale_devices(self, endpoint_ids: set[str]) -> None:
        """Remove devices confirmed absent from two complete inventory scans."""
        if not endpoint_ids:
            return
        registry = dr.async_get(self.hass)
        for endpoint_id in endpoint_ids:
            device = registry.async_get_device(
                identifiers={device_identifier(endpoint_id)}
            )
            if device is not None:
                registry.async_update_device(
                    device_id=device.id,
                    remove_config_entry_id=self.config_entry.entry_id,
                )


type AuxCloudConfigEntry = ConfigEntry[AuxCloudCoordinator]
