# AUX Cloud Integration for Home Assistant

Unofficial Home Assistant integration for AUX Cloud appliances, including AUX air conditioners and AUX heat pumps. AUX Cloud is based on the BroadLink cloud platform, so this integration communicates with the cloud service used by the mobile app instead of replacing the device Wi-Fi module.

The implementation is based on BroadLink public SDK documentation and reverse engineering of the AUX/AC Freedom Android app.

## Features

- Cloud push integration using AUX/BroadLink websocket relay as the primary update path.
- Websocket-first device control with HTTP command fallback when the websocket is unavailable or an acknowledgement fails.
- Degraded HTTP polling fallback while websocket push is unhealthy.
- Automatic one-shot session recovery when the cloud reports an expired or invalid login session.
- Home Assistant Repairs issues for cloud API outages, authentication failures, and rate limiting.
- Config flow with email or phone login, region selection, and automatic device discovery.
- Support for personal and shared AUX Cloud devices.
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
- Manual/coordinator refreshes.
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
4. Choose email or phone-number login
5. Enter your AUX Cloud credentials and region (Europe, USA, China, or Russia - based on your AUX Cloud account)
6. Finish setup and use Home Assistant's native **Name and assign** screen to set device names and areas

Supported regions are Europe, USA, China, and Russia.
For phone-number login, enter the phone number as you use it with AUX Cloud.

All discovered devices are added during initial setup. Home Assistant will offer its native name and area assignment after the entry is created. Use the integration options flow later if you want to disable individual devices.

> [!TIP]
> Make sure that your devices are online when setting up the integration. If you add a device that is offline, it may not add all the entities. Reload the integration after the device is online.

Credentials are stored in Home Assistant config entry storage. Existing email entries keep using the original email login path; phone-number login is used only for entries configured with a phone number. The integration uses stored credentials to silently recover expired cloud sessions. If recovery fails because AUX Cloud rejects the credentials, Home Assistant will raise an authentication issue.

## Usage

After setting up the integration, your AUX devices will be available in Home Assistant. Depending on the device type and supported capabilities, entities may include climate, water heater, sensor, switch, select, and number entities.

You can control them through:

- The Home Assistant UI
- Automations
- Scripts
- Voice assistants integrated with Home Assistant

## Error Handling

The integration maps known AUX/BroadLink error codes into typed failures:

- Invalid credentials or expired sessions.
- Network and DNS failures.
- Cloud server errors such as HTTP `503`.
- Rate limiting.
- Device command failures.

Home Assistant Repairs issues are created for long-lived conditions:

- **AUX Cloud API unavailable**
- **AUX Cloud authentication failed**
- **AUX Cloud rate limit reached**

API outage and rate-limit issues clear automatically after a successful refresh. Authentication issues require updating or rechecking the stored credentials.

## Troubleshooting

If you encounter issues:

1. Check the Home Assistant logs for error messages
2. Check **Settings** > **Repairs** for integration issues
3. Verify your AUX Cloud credentials and selected region are correct
4. Ensure your devices are online and accessible through the AUX Cloud app
5. If you've recently changed your password, reconfigure or reload the integration
6. If AUX Cloud is temporarily unavailable, wait for the API to recover; the integration will keep retrying automatically

If you log in through the mobile app and the cloud invalidates the previous session, the integration will attempt a silent re-login. If the stored credentials are no longer valid, Home Assistant will report an authentication issue.

## Known Issues

- **Logging in the App**: The login process in the app may invalidate existing sessions (at least on Android). The integration now attempts automatic re-login when the cloud reports an expired session. If recovery fails, check Home Assistant Repairs and reload or reconfigure the integration.
- **AUX Cloud API unavailable**: If the API is down or returns errors such as HTTP `503`, Home Assistant will create a Repairs issue and retry automatically.
- **Shared devices**: If your account has shared devices, you might encounter an issue that `Platform aux_cloud does not generate unique ids`; check your HA logs and transfer ownership of the device to your account if needed.
- **Offline devices during setup**: Devices should be online during setup. Offline devices may not expose every entity until the integration is reloaded.
- This is cloud control only. Local LAN control is not implemented.
- Device support is profile-based. Unknown product IDs may appear without entities until a profile is added.

## Tested Devices

- AUX Freedom air conditioner, model `AUX-12F2H/I`
- AUX heat pump, model `ACHP-HO8/4R3HA-I`

Known product IDs:

- Air conditioners: `c0620000`, `2a4e0000`
- Heat pumps: `c3aa0000`

## Development

Minimum Home Assistant version for HACS metadata is `2025.4.0`.

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
  - Home Assistant coordinator lifecycle, websocket runner ownership, degraded polling, pushed-update merges, and Repairs issue reporting.

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
```

## Privacy

This integration communicates with AUX Cloud servers. Credentials are stored locally by Home Assistant when configured through the UI. Device state and commands are sent to AUX Cloud because the integration uses the vendor cloud API.

## Contributing

Contributions are welcome. Please include tests for new product profiles, protocol parsing, websocket behavior, and error handling changes.
