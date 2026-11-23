"""Constants for Ring Kidde."""

from __future__ import annotations

DOMAIN = "ring_kidde"

# Ring reports Kidde alarms as "sensor_bluejay_<suffix>": s = smoke, c = CO,
# w/b = wired/battery (e.g. sc, wsc, bsc, s, ws, bs, wc, bc).
KIDDE_KIND_PREFIX = "sensor_bluejay_"

HEALTH_POLL_SECONDS = 60

# Live alarm state (Ring "clap" websocket, same as ring-client-api's Location).
TICKET_PATH = "/api/v1/clap/tickets"
DEVICE_LIST_MSG = "DeviceInfoDocGetList"
CONNECT_TIMEOUT_SECONDS = 30
RECONNECT_MIN_SECONDS = 5
RECONNECT_MAX_SECONDS = 300
# Re-fetch the full device docs this often, in case a partial update was missed.
REFRESH_LIST_SECONDS = 15 * 60


def kind_suffix(kind: str) -> str:
    """Return the part after sensor_bluejay_."""
    return kind.removeprefix(KIDDE_KIND_PREFIX)


def is_kidde_kind(kind: str | None) -> bool:
    """True for any Kidde-on-Ring alarm kind."""
    return bool(kind) and str(kind).startswith(KIDDE_KIND_PREFIX)


def kind_has_smoke(kind: str) -> bool:
    """Smoke sensing models carry an 's' in the suffix."""
    return "s" in kind_suffix(kind)


def kind_has_co(kind: str) -> bool:
    """CO sensing models end in 'c'."""
    return kind_suffix(kind).endswith("c")
