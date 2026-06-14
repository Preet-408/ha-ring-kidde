"""Sensor platform for Ring Kidde — firmware and connection diagnostics."""
from __future__ import annotations

import logging
from datetime import timedelta, datetime, timezone

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=SCAN_INTERVAL_SECONDS)

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="firmware_status",
        name="Firmware Status",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:cellphone-arrow-down",
    ),
    SensorEntityDescription(
        key="last_seen",
        name="Last Seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="wifi_signal",
        name="WiFi Signal",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:wifi",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    devices = hass.data[DOMAIN][entry.entry_id]["devices"]
    entities = [
        KiddeSensor(device, desc)
        for device in devices
        for desc in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities, True)

    async def _poll(now=None):
        for entity in entities:
            await entity.async_update()
            entity.async_write_ha_state()

    entry.async_on_unload(
        async_track_time_interval(hass, _poll, SCAN_INTERVAL)
    )


class KiddeSensor(SensorEntity):
    """Sensor for a Ring Kidde device."""

    _attr_has_entity_name = True

    def __init__(self, device, description: SensorEntityDescription) -> None:
        self._device = device
        self.entity_description = description
        self._attr_unique_id = f"ring_kidde_{device.id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._device.id))},
            name=self._device.name,
            manufacturer="Kidde",
            model=self._device.kind,
        )

    @property
    def native_value(self):
        health = self._device._attrs.get("health", {})
        key = self.entity_description.key

        if key == "firmware_status":
            return health.get("firmware_version_status")

        if key == "last_seen":
            ts = health.get("last_update_time")
            if ts:
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            return None

        if key == "wifi_signal":
            return health.get("rssi_category")

        return None

    async def async_update(self) -> None:
        pass
