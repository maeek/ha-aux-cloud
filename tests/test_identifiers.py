"""AUX registry identity compatibility tests."""

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aux_cloud.identifiers import (
    account_unique_id_from_user_id,
    collision_safe_entity_unique_id,
    device_identifier,
    legacy_entity_unique_id,
)

pytest_plugins = "pytest_homeassistant_custom_component"


def test_registry_identifiers_remain_stable():
    """Released IDs stay frozen while account IDs remain normalized."""
    assert legacy_entity_unique_id("00001234", "ac") == "aux_cloud_1234_ac"
    assert legacy_entity_unique_id("device-1", "pwr") == "aux_cloud_device-1_pwr"
    assert device_identifier("00001234") == ("aux_cloud", "00001234")
    assert account_unique_id_from_user_id("CN", "user-1") == "cn:user:user-1"


def test_second_account_uses_v2_id_for_shared_entity(hass):
    """Test overlapping multi-account devices do not collide in the registry."""
    first_entry = MockConfigEntry(domain="aux_cloud", unique_id="eu:user:first")
    second_entry = MockConfigEntry(domain="aux_cloud", unique_id="eu:user:second")
    first_entry.add_to_hass(hass)
    second_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=first_entry.entry_id,
        identifiers={("aux_cloud", "device1")},
    )
    er.async_get(hass).async_get_or_create(
        "switch",
        "aux_cloud",
        "aux_cloud_device1_pwr",
        config_entry=first_entry,
        device_id=device.id,
    )

    unique_id = collision_safe_entity_unique_id(
        hass,
        "switch",
        "device1",
        "pwr",
        {},
        config_entry_id=second_entry.entry_id,
        identity_salt=second_entry.unique_id,
    )

    assert unique_id.startswith("aux_cloud_device1_pwr_v2_")
