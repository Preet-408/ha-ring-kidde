"""Diagnostics for Ring Kidde — dumps raw Ring device data to help debug detection."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics showing raw Ring device data."""
    output = {
        "ring_kidde_config": dict(entry.data),
        "ring_entries": [],
    }

    for ring_entry in hass.config_entries.async_entries("ring"):
        ring_data = getattr(ring_entry, "runtime_data", None)
        entry_info: dict = {
            "entry_id": ring_entry.entry_id,
            "has_runtime_data": ring_data is not None,
            "devices_data_raw": {},
            "other_devices": [],
            "all_device_kinds": [],
        }

        if ring_data:
            ring_api = getattr(ring_data, "api", None)
            if ring_api:
                # Dump raw devices_data so we can see every device kind
                for family, devices in ring_api.devices_data.items():
                    entry_info["devices_data_raw"][family] = [
                        {
                            "id": d.get("id"),
                            "kind": d.get("kind"),
                            "name": d.get("description"),
                            "metadata": d.get("metadata", {}),
                            "alerts": d.get("alerts", {}),
                            "type": d.get("type"),
                        }
                        for d in devices.values()
                    ]
                    for d in devices.values():
                        entry_info["all_device_kinds"].append(
                            f"{family}/{d.get('kind')}"
                        )

            ring_devices = getattr(ring_data, "devices", None)
            if ring_devices:
                for d in getattr(ring_devices, "other", []):
                    entry_info["other_devices"].append(
                        {"id": d.id, "kind": d.kind, "name": d.name}
                    )

        output["ring_entries"].append(entry_info)

    return output
