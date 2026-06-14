"""Binary sensor platform for Ring Kidde smoke/CO detectors."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import ALERT_STATUS_CLEAR, DOMAIN, KIDDE_CO_KINDS, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=SCAN_INTERVAL_SECONDS)

BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="smoke",
        name="Smoke",
        device_class=BinarySensorDeviceClass.SMOKE,
    ),
    BinarySensorEntityDescription(
        key="co",
        name="Carbon Monoxide",
        device_class=BinarySensorDeviceClass.CO,
    ),
    BinarySensorEntityDescription(
        key="connectivity",
        name="Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    devices = hass.data[DOMAIN][entry.entry_id]["devices"]
    entities: list[KiddeBinarySensor] = []

    for device in devices:
        for description in BINARY_SENSOR_DESCRIPTIONS:
            if description.key == "co" and device.kind not in KIDDE_CO_KINDS:
                continue
            entities.append(KiddeBinarySensor(device, description))

    if not entities:
        _LOGGER.warning(
            "ring_kidde: No entities created. Check that your Kidde detector "
            "is visible in the Ring app and the Ring integration is configured."
        )

    async_add_entities(entities, True)

    async def _poll(now=None):
        for entity in entities:
            await entity.async_update()
            entity.async_write_ha_state()

    entry.async_on_unload(
        async_track_time_interval(hass, _poll, SCAN_INTERVAL)
    )


class KiddeBinarySensor(BinarySensorEntity):
    """Smoke, CO, or connectivity binary sensor."""

    _attr_has_entity_name = True

    def __init__(self, device, description: BinarySensorEntityDescription) -> None:
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
            sw_version=getattr(self._device, "firmware", None),
        )

    @property
    def is_on(self) -> bool | None:
        health = getattr(self._device, "_health_attrs", {}) or {}
        alerts = self._device._attrs.get("alerts", {})
        key = self.entity_description.key

        if key == "connectivity":
            return alerts.get("connection", "") == "online"
        if key == "smoke":
            state = health.get("smoke_status") or alerts.get("smoke") or ""
            return bool(state) and state.lower() != ALERT_STATUS_CLEAR
        if key == "co":
            state = health.get("co_status") or alerts.get("co") or ""
            return bool(state) and state.lower() != ALERT_STATUS_CLEAR
        return None

    async def async_update(self) -> None:
        try:
            await self._device.async_update_health_data()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("ring_kidde: update error for %s: %s", self._device.name, err)
