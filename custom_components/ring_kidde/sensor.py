"""Sensor platform for Ring Kidde — battery."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=SCAN_INTERVAL_SECONDS)

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="battery",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
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
            manufacturer="Kidde / Ring",
            model=self._device.kind,
        )

    @property
    def native_value(self):
        health = getattr(self._device, "_health_attrs", {}) or {}
        pct = health.get("battery_percentage")
        if pct is not None:
            try:
                return int(pct)
            except (ValueError, TypeError):
                pass
        return health.get("battery_percentage_category")

    async def async_update(self) -> None:
        try:
            await self._device.async_update_health_data()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("ring_kidde: update error for %s: %s", self._device.name, err)
