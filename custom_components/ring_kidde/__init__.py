"""Ring Kidde Smoke/CO Detector integration.

Rather than patching ring_doorbell (which breaks across versions),
we read devices_data directly from the Ring API and construct RingOther
objects ourselves for any Kidde device kinds found there.

Tracks: https://github.com/home-assistant/core/issues/152916
"""
from __future__ import annotations

import logging

from ring_doorbell.other import RingOther

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, KIDDE_SMOKE_KINDS

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["binary_sensor", "sensor"]


def get_kidde_devices(hass: HomeAssistant) -> list[RingOther]:
    """Build RingOther objects directly from Ring's raw devices_data."""
    kidde = []
    for ring_entry in hass.config_entries.async_entries("ring"):
        ring_data = getattr(ring_entry, "runtime_data", None)
        if ring_data is None:
            continue
        ring_api = getattr(ring_data, "api", None)
        if ring_api is None:
            continue

        # devices_data["other"] contains ALL other devices including Kidde.
        # The ring_doorbell library filters this down to INTERCOM_KINDS only,
        # so we bypass it and construct RingOther directly from raw data.
        other_raw = ring_api.devices_data.get("other", {})
        for device_id, device in other_raw.items():
            kind = device.get("kind", "")
            if kind in KIDDE_SMOKE_KINDS:
                _LOGGER.info(
                    "ring_kidde: Found Kidde device id=%s kind=%s name=%s",
                    device_id, kind, device.get("description"),
                )
                # RingOther needs the ring instance and the device_api_id
                # It reads its own data from ring_api.devices_data["other"][id]
                kidde.append(RingOther(ring_api, device_id, shared=True))

    return kidde


def dump_ring_data(hass: HomeAssistant) -> None:
    """Dump raw Ring device data to the log."""
    _LOGGER.warning("ring_kidde: ===== RING DEVICE DUMP =====")
    for ring_entry in hass.config_entries.async_entries("ring"):
        ring_data = getattr(ring_entry, "runtime_data", None)
        if ring_data is None:
            _LOGGER.warning("ring_kidde: No runtime_data on Ring entry")
            continue
        ring_api = getattr(ring_data, "api", None)
        if ring_api is None:
            continue
        for family, devices in ring_api.devices_data.items():
            for dev_id, dev in devices.items():
                _LOGGER.warning(
                    "ring_kidde: family=%s id=%s kind=%s name=%s",
                    family, dev_id, dev.get("kind"), dev.get("description"),
                )
    _LOGGER.warning("ring_kidde: ===== END DUMP =====")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ring Kidde."""
    devices = get_kidde_devices(hass)

    if not devices:
        _LOGGER.warning(
            "ring_kidde: No Kidde devices found. "
            "Ensure the Ring integration is loaded and your Kidde detector "
            "is added to your Ring account."
        )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"devices": devices}

    async def handle_dump(call: ServiceCall) -> None:
        dump_ring_data(hass)

    hass.services.async_register(DOMAIN, "dump_devices", handle_dump)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
