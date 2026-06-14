# Ring Kidde Smoke/CO Detector — Home Assistant Custom Integration

Surfaces **Kidde Smart Smoke and Smoke+CO detectors with Ring** (launched April 2025) in Home Assistant.

Tracks upstream issue: https://github.com/home-assistant/core/issues/152916

---

## What this does

The `ring_doorbell` Python library (used by the built-in Ring integration) filters the `other` device family to only include intercom devices, silently dropping Kidde detectors. This integration reads Kidde devices directly from the Ring API's raw device data and surfaces them as proper HA entities — no library patching required.

The Ring integration must already be configured. This integration borrows its authenticated session.

---

## Entities created per detector

### Binary Sensors

| Entity | Device Class | Notes |
|--------|-------------|-------|
| `binary_sensor.<name>_smoke` | `smoke` | On when smoke alarm is active |
| `binary_sensor.<name>_carbon_monoxide` | `co` | On when CO alarm is active (combo/CO models only) |
| `binary_sensor.<name>_connected` | `connectivity` | Online/offline status |
| `binary_sensor.<name>_ac_power` | `plug` | On when hardwired AC power is present; off if AC is lost |
| `binary_sensor.<name>_battery_problem` | `problem` | On if the backup battery has a fault |

### Sensors

| Entity | Notes |
|--------|-------|
| `sensor.<name>_firmware_status` | `Up to Date` or update available |
| `sensor.<name>_last_seen` | Timestamp of last Ring API update |
| `sensor.<name>_wifi_signal` | WiFi signal category |

### Why no battery percentage?

The Ring API returns `battery_percentage_category: "unknown"` for hardwired+battery-backup Kidde units because the device is always on AC power. Ring doesn't report a meaningful battery percentage for hardwired detectors. The `AC Power` and `Battery Problem` binary sensors are the meaningful indicators — you'll know if mains power is lost or the backup battery has a fault.

---

## Prerequisites

- Home Assistant with the built-in **Ring** integration already configured and working
- Your Kidde detector added to your Ring account and visible in the Ring app

---

## Installation

1. Copy the `custom_components/ring_kidde` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration**
4. Search for **Ring Kidde**
5. Click through the setup form — no credentials needed, it uses your existing Ring integration

---

## Supported device kinds

Confirmed working:
```
sensor_bluejay_wsc   # Smoke + CO, hardwired with battery backup  ✓ tested
```

Expected to work (same API structure, untested):
```
sensor_bluejay_ws    # Smoke only, hardwired
sensor_bluejay_wc    # CO only, hardwired
sensor_bluejay_bsc   # Smoke + CO, battery
sensor_bluejay_bs    # Smoke only, battery
sensor_bluejay_bc    # CO only, battery
```

If your device has a different `kind` value, open an issue with your Ring diagnostic dump and it can be added.

---

## Known limitations

- **Alarm state payload is unconfirmed.** The Ring API shows `"Clear"` when no alarm is active, but the exact payload for an active alarm has not been captured from a live event yet. The smoke/CO sensors will flip `on` for any non-empty, non-`"clear"` value in the health/alerts fields. If your alarm fires and the sensor doesn't trigger, open an issue with your HA diagnostic dump so the field mapping can be confirmed — run the test button on the detector to simulate an alarm.
- **This integration is temporary.** It will become unnecessary once the upstream Ring integration adds native Kidde support (tracked at issue #152916). At that point uninstall this and use the built-in Ring integration instead. PRs to both `home-assistant/python-ring-doorbell` and `home-assistant/core` are in progress.

---

## Troubleshooting

**No entities appear after install:**
Go to **Settings → System → Logs** and filter by `ring_kidde`. You should see a line like:
```
ring_kidde: Found Kidde device id=... kind=sensor_bluejay_wsc name=Kitchen
```
If you see `No Kidde devices found`, make sure the Ring integration is configured and your detector is visible in the Ring app.

**Trigger a device re-scan:**
Go to **Developer Tools → Services**, search for `ring_kidde.dump_devices`, and call it. This dumps all Ring device data to the log so you can verify what the API is returning.

---

## Contributing

If you can capture the Ring API payload during an actual alarm (trigger the test button on your detector and immediately grab the HA diagnostic dump or run `ring_health_dump.py`), please share it in issue #152916. This will let us confirm the smoke/CO alert field values and finalize the upstream PR.
