# Ring Kidde Smoke/CO Detector — Home Assistant Custom Integration

Surfaces **Kidde Smart Smoke and Smoke+CO detectors with Ring** (launched April 2025) in Home Assistant.

Tracks upstream issue: https://github.com/home-assistant/core/issues/152916

---

## What this does

The `ring_doorbell` Python library (used by the built-in Ring integration) filters the `other` device family to only include intercom devices, silently dropping Kidde detectors. This integration:

1. **Patches the library** at runtime to also include `sensor_bluejay_*` device kinds
2. **Adds binary sensors** for smoke detected, CO detected, and connectivity
3. **Adds a battery sensor** (returns category string until Ring exposes a numeric %)

---

## Entities created per detector

| Entity | Device Class | Notes |
|--------|-------------|-------|
| `binary_sensor.<name>_smoke` | `smoke` | On when smoke alarm active |
| `binary_sensor.<name>_carbon_monoxide` | `co` | On when CO alarm active (combo/CO models only) |
| `binary_sensor.<name>_connected` | `connectivity` | Online status |
| `sensor.<name>_battery` | `battery` | `full/medium/low/unknown` or `%` if API exposes it |

---

## Installation (HACS manual)

1. Copy the `custom_components/ring_kidde` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration**
4. Search for **Ring Kidde**
5. Follow the setup (Ring integration must already be configured)

---

## Known limitations

- **Alarm state payload is unconfirmed.** The Ring API returns `"Clear"` for the smoke/CO status when no alarm is active, but the exact payload for an active alarm hasn't been captured yet (device is new). The smoke/CO sensors will flip `on` for any non-empty, non-"clear" value in the alerts field. If your alarm fires and the sensor doesn't trigger, please open an issue with your HA diagnostic dump.
- **Battery is reported as a category** (`full`, `medium`, `low`, `unknown`) not a percentage, because the Ring API doesn't expose a numeric value for these devices yet.
- This integration will become unnecessary once the upstream Ring integration adds support. At that point you can uninstall this and use the built-in integration.

---

## Supported device kinds

```
sensor_bluejay_wsc   # Smoke + CO, hardwired
sensor_bluejay_ws    # Smoke only, hardwired
sensor_bluejay_wc    # CO only, hardwired
sensor_bluejay_bsc   # Smoke + CO, battery
sensor_bluejay_bs    # Smoke only, battery
sensor_bluejay_bc    # CO only, battery
```

If your device shows a different `kind` value in the Ring diagnostics, open an issue and we can add it.

---

## Contributing / testing

If you have one of these devices and can capture the Ring API payload during an alarm (use a match or test button), please share the diagnostics data in the GitHub issue so the alert state mapping can be confirmed.
