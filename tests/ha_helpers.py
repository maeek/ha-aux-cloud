"""Home Assistant test helpers shared by the minimum and current Core releases."""

from importlib.util import find_spec

if find_spec("pytest_homeassistant") is not None:
    from pytest_homeassistant.common import MockConfigEntry
else:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

__all__ = ["MockConfigEntry"]
