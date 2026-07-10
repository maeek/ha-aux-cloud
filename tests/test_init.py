"""Test component setup."""

import pytest
from homeassistant.helpers.translation import async_get_translations

from custom_components.aux_cloud.const import DOMAIN
from custom_components.aux_cloud.select import SELECTS


@pytest.mark.parametrize("language", ("en", "el", "pl"))
async def test_select_options_have_translations(hass, language):
    """Test every select option exposes a localized label to the frontend."""
    translations = await async_get_translations(
        hass, language, "entity", integrations={DOMAIN}
    )

    for select in SELECTS.values():
        translation_key = select["description"].translation_key
        for option in select["state_icons"]:
            assert (
                "component.aux_cloud.entity.select."
                f"{translation_key}.state.{option}" in translations
            )
