"""Constants for Ring Kidde integration."""

DOMAIN = "ring_kidde"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_TOKEN = "token"
CONF_2FA = "two_factor_code"

# Device kind strings reported by the Ring API for Kidde devices
KIDDE_SMOKE_KINDS = [
    "sensor_bluejay_wsc",   # Smoke + CO combo (hardwired)
    "sensor_bluejay_ws",    # Smoke only (hardwired)
    "sensor_bluejay_wc",    # CO only (hardwired)
    "sensor_bluejay_bsc",   # Smoke + CO combo (battery)
    "sensor_bluejay_bs",    # Smoke only (battery)
    "sensor_bluejay_bc",    # CO only (battery)
]

KIDDE_CO_KINDS = [
    "sensor_bluejay_wsc",
    "sensor_bluejay_wc",
    "sensor_bluejay_bsc",
    "sensor_bluejay_bc",
]

ALERT_STATUS_CLEAR = "clear"
SCAN_INTERVAL_SECONDS = 30
USER_AGENT = "ring_kidde_ha/0.1"
