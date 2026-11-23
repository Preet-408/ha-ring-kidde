"""Diagnostics: REST health records and recent live websocket messages (redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import KiddeData, rest_data

TO_REDACT = {
    "location_id", "owner_id", "user_id", "latitude", "longitude", "geo_coordinates",
    "mac_address", "macAddress", "amazon_device_serial_number", "serialNumber",
    "ticket", "authcode", "email", "address",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    data: KiddeData = entry.runtime_data
    return async_redact_data(
        {
            "devices": [
                {"id": d.id, "kind": d.kind, "name": d.name, "rest": rest_data(hass, d)}
                for d in data.devices
            ],
            "live": [
                {
                    "connected": c.connected,
                    "last_error": c.last_error,
                    "assets": c.assets,
                    "docs": c.docs,
                    "recent_messages": list(c.samples),
                }
                for c in data.clients.values()
            ],
        },
        TO_REDACT,
    )
