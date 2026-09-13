"""Stable AUX account, device, and entity identifiers."""

from __future__ import annotations

import hashlib

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN


def account_unique_id_from_user_id(region: str, user_id: str) -> str:
    """Return the stable account ID used for authenticated entries."""
    return f"{(region or 'eu').strip().lower()}:user:{user_id}"


def legacy_entity_unique_id(endpoint_id: str, entity_key: str) -> str:
    """Return the immutable unique ID used by released AUX entities."""
    return f"{DOMAIN}_{endpoint_id.lstrip('0')}_{entity_key}"


def device_identifier(endpoint_id: str) -> tuple[str, str]:
    """Return the immutable raw endpoint device-registry identifier."""
    return (DOMAIN, endpoint_id)


def collision_safe_entity_unique_id(
    hass: HomeAssistant,
    entity_domain: str,
    endpoint_id: str,
    entity_key: str,
    reserved: dict[tuple[str, str], str],
    *,
    config_entry_id: str | None = None,
    identity_salt: str = "",
) -> str:
    """Preserve legacy IDs and use deterministic V2 IDs only for collisions."""
    legacy_id = legacy_entity_unique_id(endpoint_id, entity_key)
    digest_source = f"{endpoint_id}\0{identity_salt}"
    digest = hashlib.sha256(digest_source.encode()).hexdigest()[:8]
    candidates = (legacy_id, f"{legacy_id}_v2_{digest}")
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    for candidate in candidates:
        reservation = (entity_domain, candidate)
        entity_id = entity_registry.async_get_entity_id(
            entity_domain, DOMAIN, candidate
        )
        entry = entity_registry.async_get(entity_id) if entity_id else None
        if entry is not None:
            if config_entry_id is not None and entry.config_entry_id != config_entry_id:
                continue
            device = (
                device_registry.async_get(entry.device_id) if entry.device_id else None
            )
            if device and device_identifier(endpoint_id) in device.identifiers:
                reserved[reservation] = endpoint_id
                return candidate
            continue
        if reserved.get(reservation, endpoint_id) == endpoint_id:
            reserved[reservation] = endpoint_id
            return candidate

    full_digest = hashlib.sha256(digest_source.encode()).hexdigest()
    unique_id = f"{legacy_id}_v2_{full_digest}"
    reserved[(entity_domain, unique_id)] = endpoint_id
    return unique_id
