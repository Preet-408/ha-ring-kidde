"""Diagnostic sensors from the Ring integration's polled device data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import KiddeData, KiddeDevice, live_doc_for, rest_data, signal_update
from .binary_sensor import device_info
from .const import HEALTH_POLL_SECONDS


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data: KiddeData = entry.runtime_data
    entities: list[SensorEntity] = [KiddeLastSeenSensor(hass, d) for d in data.devices]
    entities += [KiddeBatteryStatusSensor(entry, d) for d in data.devices]
    async_add_entities(entities)


class KiddeLastSeenSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Last seen"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, device: KiddeDevice) -> None:
        self._device = device
        self._attr_unique_id = f"ring_kidde_{device.id}_last_seen"
        self._attr_device_info = device_info(device)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._tick,
                timedelta(seconds=HEALTH_POLL_SECONDS),
            )
        )

    @callback
    def _tick(self, _now) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> datetime | None:
        ts = (rest_data(self.hass, self._device).get("health") or {}).get("last_update_time")
        return datetime.fromtimestamp(ts, UTC) if isinstance(ts, (int, float)) else None

    @property
    def extra_state_attributes(self):
        health = rest_data(self.hass, self._device).get("health") or {}
        return {"firmware": health.get("firmware_version_status")}


class KiddeBatteryStatusSensor(SensorEntity):
    """Backup battery status as Ring reports it (e.g. 'full'); Ring gives no percentage."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Backup battery"
    _attr_icon = "mdi:battery-heart-variant"

    def __init__(self, entry: ConfigEntry, device: KiddeDevice) -> None:
        self._entry = entry
        self._device = device
        self._attr_unique_id = f"ring_kidde_{device.id}_battery_status"
        self._attr_device_info = device_info(device)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._entry.entry_id), self.async_write_ha_state
            )
        )

    @property
    def _status(self) -> str | None:
        doc = live_doc_for(self.hass, self._entry, self._device)
        value = (doc or {}).get("batteryStatus")
        return str(value) if value not in (None, "") else None

    @property
    def available(self) -> bool:
        data: KiddeData = self._entry.runtime_data
        client = data.clients.get(self._device.location_id)
        return bool(client and client.connected and self._status is not None)

    @property
    def native_value(self) -> str | None:
        return self._status
