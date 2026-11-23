# Ring Kidde Smoke/CO for Home Assistant (Preet-408 fork)

Fork of [tboggiano/ha-ring-kidde](https://github.com/tboggiano/ha-ring-kidde) (MIT).
Adds Kidde smoke/CO alarms that are set up in the **Ring app** (Ring reports them as
`sensor_bluejay_*`, which Home Assistant's Ring integration ignores; see
[home-assistant/core#152916](https://github.com/home-assistant/core/issues/152916)).

## What changed from upstream
- **Live smoke/CO.** Ring pushes alarm state over its websocket, not the REST device list.
  `live.py` opens that websocket (ticket from `clap/tickets`, then `wss://<host>/ws`,
  then `DeviceInfoDocGetList`), the way ring-client-api's `Location` does, and accepts
  Kidde assets so accounts without a Ring Alarm hub work. Smoke/CO only turn on for an
  explicit `alarmStatus: active`; anything unknown leaves them unavailable, never "on".
- **All Kidde kinds** (`sensor_bluejay_sc` included), smoke/CO decided from the kind suffix.
- **No second Ring login.** Uses the Ring integration's session; upstream stored its own
  Ring token (and printed it in diagnostics).
- Diagnostics are redacted and include recent live messages for debugging.

## Entities (per alarm)
- `binary_sensor.<name>_smoke`, `binary_sensor.<name>_carbon_monoxide` (live; unavailable when the live link is down)
- `binary_sensor.<name>_online`, `binary_sensor.<name>_battery_problem`, `sensor.<name>_last_seen` (from the Ring integration's poll)
- `binary_sensor.kidde_live_alarm_link` per Ring location

## Install
Requires the core Ring integration. Copy `custom_components/ring_kidde` into `/config/custom_components/`,
restart Home Assistant, then add **Ring Kidde Smoke/CO**. Test with the alarm's test button.

**Not a replacement for the alarms themselves or Ring's own notifications.**
