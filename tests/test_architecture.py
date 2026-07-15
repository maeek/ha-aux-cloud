"""Guard the public API and Home Assistant adapter boundary."""

from __future__ import annotations

import ast
from pathlib import Path

COMPONENT = Path(__file__).parents[1] / "custom_components" / "aux_cloud"


def _imports(path: Path) -> list[ast.Import | ast.ImportFrom]:
    tree = ast.parse(path.read_text(), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]


def test_public_client_and_dna_have_no_home_assistant_dependency() -> None:
    """Keep the replaceable cloud implementation independent from HA."""
    paths = [
        *sorted((COMPONENT / "api").glob("*.py")),
        *sorted((COMPONENT / "dna").glob("*.py")),
        COMPONENT / "device_metadata.py",
        COMPONENT / "devices.py",
    ]

    violations = []
    for path in paths:
        for imported in _imports(path):
            names = (
                [alias.name for alias in imported.names]
                if isinstance(imported, ast.Import)
                else [imported.module or ""]
            )
            if any(
                name == "homeassistant" or name.startswith("homeassistant.")
                for name in names
            ):
                violations.append(path.relative_to(COMPONENT))

    assert not violations


def test_only_composition_roots_import_the_dna_implementation() -> None:
    """Keep Home Assistant runtime code dependent on the public contract."""
    allowed = {COMPONENT / "__init__.py", COMPONENT / "config_flow.py"}
    violations = [
        path.relative_to(COMPONENT)
        for path in COMPONENT.glob("*.py")
        for imported in _imports(path)
        if isinstance(imported, ast.ImportFrom)
        and imported.level == 1
        and imported.module == "dna"
        and path not in allowed
    ]

    assert not violations
