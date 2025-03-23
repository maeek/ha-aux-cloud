# AUX Cloud Integration for Home Assistant

Unofficial integration for AUX Cloud connected appliances like air conditioners and heat pumps. AUX Cloud is a service
based on the Broadlink platform that allows you to control your appliances from anywhere. This integration provides a
way to control your AUX devices through Home Assistant without needing to replace hardware.

## Features

- Control AUX air conditioners and heat pumps from Home Assistant
- View device status and sensor readings
- Support for both personal and shared devices
- Secure credential storage (when configured through UI)

## Installation

### HACS Installation (Recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed
2. Go to HACS > Integrations
3. Click the "+" button and search for "AUX Cloud"
4. Install the integration
5. Restart Home Assistant

### Manual Installation

1. Download this repository
2. Copy the `custom_components/aux_cloud` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

### UI Configuration (Recommended)

The recommended way to set up this integration is through the Home Assistant UI:

1. Go to **Settings** > **Devices & Services**
2. Click the **+ Add Integration** button
3. Search for "AUX Cloud" and select it
4. Enter your AUX Cloud email and password
5. Select which devices you want to add to Home Assistant

Your credentials will be stored securely in Home Assistant's encrypted storage.

### Configuration.yaml (Alternative)

If you prefer, you can also configure the integration through `configuration.yaml`:

```yaml
# Example configuration.yaml entry
aux_cloud:
  email: your_email@example.com
  password: your_password
```

**Note:** Credentials stored in configuration.yaml are not encrypted. For better security, the UI configuration method
is recommended.

## Usage

After setting up the integration, your AUX devices will be available as climate entities in Home Assistant. You can
control them through:

- The Home Assistant UI
- Automations
- Scripts
- Voice assistants integrated with Home Assistant

## Troubleshooting

If you encounter issues:

1. Check the Home Assistant logs for error messages
2. Verify your AUX Cloud credentials are correct
3. Ensure your devices are online and accessible through the AUX Cloud app
4. If you've recently changed your password, you'll need to reconfigure the integration

## Development

This integration is still in development. Current status:

- [x] Reverse engineer the AUX Cloud API
- [x] [API] Implement login
- [x] [API] Implement getting devices information
- [x] [Home Assistant] Config flow with device selection
- [ ] [API] Implement updating device state
- [ ] [Home Assistant] Cloud data fetcher
- [ ] [Home Assistant] Data coordinator
- [ ] [Home Assistant] climate entity
- [x] [Home Assistant] sensor entity
- [ ] [Home Assistant] binary sensor entity
- [ ] [Home Assistant] number entity
- [ ] [Home Assistant] services
- [x] Documentation
- [ ] Add to HACS
- [ ] Translations

## Privacy

This integration communicates with the AUX Cloud servers but stores your credentials locally in Home Assistant's
encrypted storage (when configured through the UI). No data is shared with third parties beyond what's necessary to
communicate with AUX Cloud services.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.