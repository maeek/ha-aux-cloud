from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.aux_cloud.api.const import AUX_MODEL_TO_NAME
from custom_components.aux_cloud.const import _LOGGER, DOMAIN


class BaseEntity(CoordinatorEntity):
    def __init__(self, coordinator, device_id, entity_description):
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_has_entity_name = True
        self.entity_description = entity_description
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{self.entity_description.key}"
    
    @property
    def device_info(self):
        """Return the device info."""
        dev = self.coordinator.get_device_by_endpoint_id(self._device_id)
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "connections": {(CONNECTION_NETWORK_MAC, dev["mac"])} if "mac" in dev else None,
            "name": self.coordinator.get_device_by_endpoint_id(self._device_id).get('friendlyName', 'AUX'),
            "manufacturer": "AUX",
            "model": AUX_MODEL_TO_NAME[dev["productId"]] or "Unknown",
        }
    
    async def _set_device_params(self, params: dict):
        """Set parameters on the device."""
        _LOGGER.debug("Setting %s for device %s", params, self.coordinator.get_device_by_endpoint_id(self._device_id)["friendlyName"])

        await self.coordinator.api.set_device_params(self.coordinator.get_device_by_endpoint_id(self._device_id), params)
        await self.coordinator.async_request_refresh()