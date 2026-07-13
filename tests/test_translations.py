"""Focused AUX Cloud tests."""

import json
from pathlib import Path


def test_error_reporting_translation_keys_exist():
    """Test all error reporting translation keys exist in bundled languages."""
    translation_dir = (
        Path(__file__).parents[1] / "custom_components" / "aux_cloud" / "translations"
    )
    config_error_keys = {
        "bad_credentials",
        "session_expired",
        "api_unavailable",
        "rate_limited",
        "cannot_connect",
        "unknown",
    }
    exception_keys = {
        "api_unavailable",
        "cannot_connect",
        "device_error",
        "invalid_auth",
        "invalid_operation",
        "invalid_option",
        "rate_limited",
        "session_expired",
        "unknown",
    }

    for language in ("en", "pl", "el"):
        translations = json.loads((translation_dir / f"{language}.json").read_text())
        assert config_error_keys <= set(translations["config"]["error"])
        assert config_error_keys <= set(translations["config"]["abort"])
        assert exception_keys <= set(translations["exceptions"])

    strings = json.loads(
        (translation_dir.parent / "strings.json").read_text(encoding="utf-8")
    )
    english = json.loads((translation_dir / "en.json").read_text(encoding="utf-8"))
    assert strings == english
