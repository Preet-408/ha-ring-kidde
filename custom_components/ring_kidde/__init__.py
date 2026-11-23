"""Ring Kidde smoke/CO alarms (fork of tboggiano/ha-ring-kidde).

Health (online, battery problem, last seen) comes from the Ring integration's
own device data. Live smoke/CO state comes from Ring's websocket (live.py).
No separate Ring login: this rides on the Ring integration's session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, is_kidde_kind
from .live import KiddeLiveClient

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


def signal_update(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_update"


@dataclass
class KiddeDevice:
    """A Kidde alarm as listed by the Ring REST API."""

    id: int
    ring_entry_id: str
    location_id: str
    kind: str
    name: str


@dataclass
class KiddeData:
    devices: list[KiddeDevice]
    clients: dict[str, KiddeLiveClient] = field(default_factory=dict)


def ring_api_for(hass: HomeAssistant, ring_entry_id: str) -> Any:
    """The Ring integration's API object (changes if Ring reloads)."""
    ring_entry = hass.config_entries.async_get_entry(ring_entry_id)
    data = getattr(ring_entry, "runtime_data", None) if ring_entry else None
    return getattr(data, "api", None)


def rest_data(hass: HomeAssistant, device: KiddeDevice) -> dict[str, Any]:
    """Latest REST record for a device, from the Ring integration's poll."""
    api = ring_api_for(hass, device.ring_entry_id)
    if api is None:
        return {}
    return (api.devices_data.get("other") or {}).get(device.id) or {}


def find_kidde_devices(hass: HomeAssistant) -> list[KiddeDevice]:
    found: list[KiddeDevice] = []
    for ring_entry in hass.config_entries.async_entries("ring"):
        api = ring_api_for(hass, ring_entry.entry_id)
        if api is None:
            continue
        for dev_id, dev in (api.devices_data.get("other") or {}).items():
            if is_kidde_kind(dev.get("kind")) and dev.get("location_id"):
                found.append(
                    KiddeDevice(
                        id=dev_id,
                        ring_entry_id=ring_entry.entry_id,
                        location_id=str(dev["location_id"]),
                        kind=str(dev["kind"]),
                        name=dev.get("description") or dev.get("name") or str(dev_id),
                    )
                )
    return found


def _norm(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value).strip().lower().replace(":", "").replace("-", "")
    return text if len(text) >= 4 else None


def live_doc_for(hass: HomeAssistant, entry: ConfigEntry, device: KiddeDevice) -> dict[str, Any] | None:
    """Find the websocket doc for a REST device (by name, MAC, serial or id)."""
    data: KiddeData = entry.runtime_data
    client = data.clients.get(device.location_id)
    if client is None or not client.docs:
        return None
    rest = rest_data(hass, device)
    keys = {
        _norm(device.name),
        _norm(rest.get("mac_address")),
        _norm((rest.get("metadata") or {}).get("amazon_device_serial_number")),
        _norm(device.id),
        _norm(rest.get("doorbot_id_str")),
    } - {None}
    assets = {a.get("uuid"): a for a in client.assets}
    for zid, doc in client.docs.items():
        values = {_norm(v) for v in doc.values()}
        asset = assets.get(client.doc_src.get(zid), {})
        values |= {_norm(v) for v in asset.values()}
        if keys & (values - {None}):
            return doc
    # One Kidde alarm in the location and one alarm doc: no ambiguity.
    kidde_here = [d for d in data.devices if d.location_id == device.location_id]
    alarm_docs = [d for d in client.docs.values() if "alarm.smoke" in (d.get("components") or {})]
    if len(kidde_here) == 1 and len(alarm_docs) == 1:
        return alarm_docs[0]
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    devices = find_kidde_devices(hass)
    if not devices:
        raise ConfigEntryNotReady("No Kidde alarms in the Ring integration yet")

    data = KiddeData(devices=devices)
    entry.runtime_data = data

    @callback
    def _changed() -> None:
        async_dispatcher_send(hass, signal_update(entry.entry_id))

    for location_id in sorted({d.location_id for d in devices}):
        ring_entry_id = next(d.ring_entry_id for d in devices if d.location_id == location_id)
        data.clients[location_id] = KiddeLiveClient(
            hass,
            lambda rid=ring_entry_id: ring_api_for(hass, rid),
            location_id,
            _changed,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    for client in data.clients.values():
        client.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data: KiddeData = entry.runtime_data
    for client in data.clients.values():
        await client.stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
