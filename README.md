# AUX Cloud Integration for Home Assistant

Unofficial Home Assistant integration for AUX Cloud appliances, including AUX air conditioners and AUX heat pumps. AUX Cloud is based on the BroadLink cloud platform, so this integration communicates with the cloud service used by the mobile app instead of replacing the device Wi-Fi module.

The implementation is based on BroadLink public SDK documentation and reverse engineering of the AUX/AC Freedom Android app.

## Features

- Cloud push integration using AUX/BroadLink websocket relay as the primary update path.
- Websocket-first device control with HTTP command fallback when the websocket is unavailable or an acknowledgement fails.
- Degraded HTTP polling fallback while websocket push is unhealthy.
- Automatic one-shot session recovery when the cloud reports an expired or invalid login session.
- Verified TLS, bounded request timeouts, rate-limit backoff, and serialized device commands.
- Email-first config flow with Europe selected by default, optional phone login, and multiple accounts.
- Native reauthentication, reconfiguration, and redacted diagnostics.
- Support for personal and shared AUX Cloud devices.
- Dynamic device discovery: devices added in AUX Cloud appear without reloading Home Assistant.
- Product profiles for AUX air conditioners and heat pumps, including v3 heat-pump quirks.
- Localized config, entity, exception, and Repairs text in English, Polish, and Greek.

## Supported Entities

Entity availability depends on the device product profile and the capabilities reported by AUX Cloud.

- `climate`
  - AUX air conditioner
  - AUX heat-pump central heating
- `water_heater`
  - Heat-pump domestic hot water
- `sensor`
  - Ambient temperature
  - Target temperature
  - Hot water target temperature
  - Hot water tank temperature
  - AUX error flag
- `switch`
  - Power controls
  - Eco mode
  - Fast hot water
  - Auxiliary heat
  - Self cleaning
  - Child lock
  - Comfortable wind
  - Health mode
  - Mildew proof
  - Sleep mode
  - Screen display
  - Power limit
- `select`
  - Quiet mode
  - Automatic water temperature
- `number`
  - Power limit percentage

## How It Works

Normal operation is push-based. After login and device bootstrap, the coordinator starts one supervised websocket runner. Websocket messages are merged directly into Home Assistant coordinator data.

HTTP is still used for:

- Login and initial device bootstrap.
- Authoritative inventory scans every 30 minutes, or five-minute fallback scans while push is unavailable.
- Device command fallback when websocket control is unavailable or rejected.
- Slow degraded polling while websocket push is unhealthy.

When websocket health is restored, degraded polling is disabled again. The integration keeps `iot_class` as `cloud_push` because normal operation is push-based.

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=maeek&repository=ha-aux-cloud&category=integration)
[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=aux_cloud)

## HACS Installation (Recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed
2. Go to HACS > Integrations
3. Search for "AUX Cloud", or add `maeek/ha-aux-cloud` as a custom HACS integration repository
4. Install the integration
5. Restart Home Assistant

## Manual Installation

1. Download this repository
2. Copy the `custom_components/aux_cloud` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

## UI Configuration (Recommended)

The recommended way to set up this integration is through the Home Assistant UI:

1. Go to **Settings** > **Devices & services**.
2. Click the **+ Add Integration** button
3. Search for "AUX Cloud" and select it
4. Choose email login (recommended for European accounts) or phone-number login
5. Enter your AUX Cloud credentials and region (Europe is the default)
6. Finish setup and use Home Assistant's native **Name and assign** screen to set device names and areas

Supported regions are Europe, Other Areas / USA, China, and Russia. Europe is
preselected for the email-first setup flow; the stored `usa` region value and
existing config entries remain backward compatible.
For phone-number login, enter the phone number as you use it with AUX Cloud.

All cloud devices are added automatically. Devices added to the account later are discovered during the next inventory scan. Disable individual entities in Home Assistant's entity registry when they are not useful.

> [!TIP]
> Make sure that your devices are online when setting up the integration. If you add a device that is offline, it may not add all the entities. Reload the integration after the device is online.

Credentials are stored in Home Assistant config entry storage. Existing email entries keep using the original email login path; phone-number login is used only for entries configured with a phone number. Existing config-entry, device, and entity unique IDs are preserved during migration. If silent session recovery fails, Home Assistant starts its native reauthentication flow.

## Usage

After setting up the integration, your AUX devices will be available in Home Assistant. Depending on the device type and supported capabilities, entities may include climate, water heater, sensor, switch, select, and number entities.

You can control them through:

- The Home Assistant UI
- Automations
- Scripts
- Voice assistants integrated with Home Assistant

### Example use cases

- Pre-heat or cool a room on a schedule while retaining AUX Cloud app access.
- Coordinate domestic hot water with electricity tariffs or photovoltaic production.
- Alert when the diagnostic error flag becomes available and non-zero.

### Automation example

The entity ID is assigned by Home Assistant and may differ from this example:

```yaml
automation:
  - alias: Cool bedroom before evening
    triggers:
      - trigger: time
        at: "19:00:00"
    actions:
      - action: climate.set_temperature
        target:
          entity_id: climate.bedroom_air_conditioner
        data:
          hvac_mode: cool
          temperature: 23
```

## Removal

Remove the AUX Cloud entry from **Settings > Devices & services**. Home Assistant unloads the websocket and all platforms and removes the entry's devices and entities. Removing the integration does not delete devices or data from AUX Cloud.

## Error Handling

The integration maps known AUX/BroadLink error codes into typed failures:

- Invalid credentials or expired sessions.
- Network and DNS failures.
- Cloud server errors such as HTTP `503`.
- Rate limiting.
- Device command failures.

Transient API outages use Home Assistant's coordinator retry behavior and are logged once per outage. HTTP `Retry-After` is honored for rate limits. Authentication failures start Home Assistant's reauthentication flow because they require user action.

## Troubleshooting

If you encounter issues:

1. Check the Home Assistant logs for error messages
2. Open the integration entry and download diagnostics; credentials and device identifiers are redacted
3. Verify your AUX Cloud credentials and selected region are correct
4. Ensure your devices are online and accessible through the AUX Cloud app
5. If you've recently changed your password, reconfigure or reload the integration
6. If AUX Cloud is temporarily unavailable, wait for the API to recover; the integration keeps retrying automatically

If you log in through the mobile app and the cloud invalidates the previous session, the integration attempts a single-flight silent re-login. If the stored credentials are no longer valid, Home Assistant prompts for reauthentication.

## Known Issues

- **Logging in the App**: The login process in the app may invalidate existing sessions (at least on Android). The integration now attempts automatic re-login when the cloud reports an expired session. If recovery fails, check Home Assistant Repairs and reload or reconfigure the integration.
- **AUX Cloud API unavailable**: If the API is down or returns errors such as HTTP `503`, Home Assistant will create a Repairs issue and retry automatically.
- **Shared device identity**: AUX endpoint IDs are used unchanged for device identifiers. A cloud account exposing the same endpoint more than once is deduplicated.
- **Offline devices**: Offline devices remain visible but may not expose every capability until a later successful inventory scan.
- This is cloud control only. Local LAN control is not implemented.
- Device support is profile-based. Unknown product IDs may appear without entities until a profile is added.

## Tested Devices

- AUX Freedom air conditioner, model `AUX-12F2H/I`
- AUX heat pump, model `ACHP-HO8/4R3HA-I`

Known product IDs:

- Standard air conditioners: `c0620000`, `2a4e0000`, `7faf0000`, `82af0000`
- Half-degree air conditioner: `1f620000`
- Air conditioners without auto mode and with extended fan levels: `28620000`,
  `c5510000`
- Multi-split air conditioner: `45620000` (no auto mode or power-limit controls)
- VRV air conditioners: `56ac0000`, `a44e0000` (vertical swing and conservative
  low/medium/high fan controls)
- Air-conditioner sub-device: `c9100100` (limited safe parameter set)
- Heat pumps: `c3aa0000`

The product profiles expose only controls verified from the AC Freedom app.
Unsupported modes, fan values, swing axes, and parameters are rejected before a
cloud command is sent. Existing unique IDs and device identifiers are unchanged.

## Development

Minimum Home Assistant version is `2026.4.0`.

This is a HACS custom integration and therefore cannot claim an official Home Assistant quality tier. [`quality_scale.yaml`](custom_components/aux_cloud/quality_scale.yaml) tracks technical alignment with the cumulative rules. Coverage above 95% and fully strict typing remain explicitly open before the file can represent complete Platinum alignment.

Current architecture:

- `custom_components/aux_cloud/api`
  - Public HA-facing API surface in `api/__init__.py`.
  - `client.py` facade for auth/session/device cache and public API methods.
  - `session.py` HTTP session, encrypted login payloads, error decoding, and session recovery.
  - `repository.py` family/device discovery and bootstrap.
  - `control.py` websocket-first, HTTP-fallback command orchestration.
  - `transports/http.py` and `transports/websocket.py` transport-specific behavior.
  - `protocol/common.py` and `protocol/websocket.py` pure wire-format helpers.
- `custom_components/aux_cloud/devices`
  - `profiles.py` product capabilities and product-specific command/bootstrap rules.
  - `normalizers.py` product-specific parameter normalization.
- `custom_components/aux_cloud/coordinator.py`
  - Typed config-entry runtime data, websocket runner ownership, dynamic inventory, stale-device reconciliation, degraded polling, and serialized command transactions.

## Testing

This document describes how to run tests and perform code quality checks for the AUX Cloud Integration.

## Prerequisites

Before running tests, ensure you have all the required dependencies installed:

```bash
pip install -r requirements.test.txt
```

## Running Tests with pytest

### Basic Test Run

Run all tests:

```bash
pytest
```

The current verification command used by maintainers is:

```bash
pytest -q
```

### Test with Coverage Reporting

Run tests and show coverage information:

```bash
pytest --cov=custom_components
```

## Code Quality Checks with pylint

### Basic pylint Check

Run pylint on the entire component:

```bash
pylint custom_components/aux_cloud
```

For the current websocket/API refactor, the focused pylint command is:

```bash
pylint custom_components/aux_cloud/__init__.py custom_components/aux_cloud/coordinator.py custom_components/aux_cloud/api custom_components/aux_cloud/devices custom_components/aux_cloud/util.py
```

### Diff whitespace check

```bash
git diff --check
```

### Code formatting

The project uses [Black](https://pypi.org/project/black/) for code formatting. To format the code, run:

```bash
black custom_components/aux_cloud

ruff check custom_components/aux_cloud tests
mypy custom_components/aux_cloud
```

## Privacy

This integration communicates with AUX Cloud servers. Credentials are stored locally by Home Assistant when configured through the UI. Device state and commands are sent to AUX Cloud because the integration uses the vendor cloud API.

## Contributing

Contributions are welcome. Please include tests for new product profiles, protocol parsing, websocket behavior, and error handling changes.
