from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.aux_cloud.api.const import AUX_MODEL_TO_NAME
from custom_components.aux_cloud.const import _LOGGER, DOMAIN, MANUFACTURER


class BaseEntity(CoordinatorEntity):
    def __init__(self, coordinator, device_id, entity_description):
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = self.coordinator.get_device_by_endpoint_id(self._device_id)
        self._attr_has_entity_name = True
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{DOMAIN}_{device_id.lstrip('0')}_{self.entity_description.key}"
        )

    @property
    def device_info(self):
        """Return the device info."""
        return DeviceInfo(
            connections=(
                {(CONNECTION_NETWORK_MAC, self._device["mac"])}
                if "mac" in self._device
                else None
            ),
            identifiers={(DOMAIN, self._device_id)},
            name=self._device.get("friendlyName", "AUX"),
            manufacturer=MANUFACTURER,
            model=AUX_MODEL_TO_NAME.get(self._device.get("productId", None), "Unknown"),
        )

    @property
    def available(self):
        """Return True if entity is available."""
        return (
            self._device is not None
            or self._device.get("endpointId") is not None
            or len(self._device.get("params", {}).keys()) > 0
        )

    @callback
    def _handle_coordinator_update(self):
        self._device = self.coordinator.get_device_by_endpoint_id(self._device_id)
        self._attr_available = self._device is not None

        self.async_write_ha_state()

    def _get_device_params(self):
        return self._device.get("params", {})

    async def _set_device_params(self, params: dict):
        """Set parameters on the device."""
        _LOGGER.debug("Setting %s for device %s", params, self._device["friendlyName"])

        await self.coordinator.api.set_device_params(self._device, params)
        await self.coordinator.async_request_refresh()
