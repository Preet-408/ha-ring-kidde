"""Binary sensors: live smoke/CO, plus online, battery problem and live-link status."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from . import KiddeData, KiddeDevice, live_doc_for, rest_data, signal_update
from .const import DOMAIN, HEALTH_POLL_SECONDS, kind_has_co, kind_has_smoke
from .live import KiddeLiveClient, alarm_state, end_of_life, malfunctions, test_in_progress


def device_info(device: KiddeDevice) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, str(device.id))},
        name=device.name,
        manufacturer="Kidde",
        model=device.kind,
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data: KiddeData = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for device in data.devices:
        if kind_has_smoke(device.kind):
            entities.append(KiddeAlarmSensor(hass, entry, device, "smoke"))
        if kind_has_co(device.kind):
            entities.append(KiddeAlarmSensor(hass, entry, device, "co"))
        entities.append(KiddeDocSensor(hass, entry, device, "end_of_life"))
        entities.append(KiddeDocSensor(hass, entry, device, "test"))
        entities.append(KiddeDocSensor(hass, entry, device, "malfunction"))
        entities.append(KiddeOnlineSensor(hass, device))
        entities.append(KiddeBatteryProblemSensor(hass, device))
    for client in data.clients.values():
        entities.append(KiddeLiveLinkSensor(entry, client))
    async_add_entities(entities)


class _LiveEntity(BinarySensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._entry.entry_id), self.async_write_ha_state
            )
        )


class KiddeAlarmSensor(_LiveEntity):
    """Smoke or CO, pushed live from Ring. Unavailable when the live link is down,
    so an alert on 'unavailable' catches a silent failure."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device: KiddeDevice, key: str) -> None:
        super().__init__(entry)
        self._device = device
        self._key = key
        self._attr_unique_id = f"ring_kidde_{device.id}_{key}"
        self._attr_device_info = device_info(device)
        if key == "smoke":
            self._attr_name = "Smoke"
            self._attr_device_class = BinarySensorDeviceClass.SMOKE
        else:
            self._attr_name = "Carbon monoxide"
            self._attr_device_class = BinarySensorDeviceClass.CO

    @property
    def _client(self) -> KiddeLiveClient | None:
        data: KiddeData = self._entry.runtime_data
        return data.clients.get(self._device.location_id)

    @property
    def _doc(self):
        return live_doc_for(self.hass, self._entry, self._device)

    @property
    def available(self) -> bool:
        client = self._client
        return bool(client and client.connected and alarm_state(self._doc, self._key) is not None)

    @property
    def is_on(self) -> bool | None:
        return alarm_state(self._doc, self._key)

    @property
    def extra_state_attributes(self):
        client = self._client
        return {
            "live_link": bool(client and client.connected),
            "matched_live_device": self._doc is not None,
        }


class KiddeLiveLinkSensor(_LiveEntity):
    """Is Home Assistant connected to Ring's live alarm feed for this location?"""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Kidde live alarm link"
    _attr_has_entity_name = False

    def __init__(self, entry: ConfigEntry, client: KiddeLiveClient) -> None:
        super().__init__(entry)
        self._client = client
        self._attr_unique_id = f"ring_kidde_live_link_{client.location_id}"

    @property
    def is_on(self) -> bool:
        return self._client.connected

    @property
    def extra_state_attributes(self):
        return {
            "last_error": self._client.last_error,
            "live_devices": len(self._client.docs),
        }


class _RestSensor(BinarySensorEntity):
    """Health from the Ring integration's polled device data."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, device: KiddeDevice) -> None:
        self._device = device
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
    def _rest(self):
        return rest_data(self.hass, self._device)

    @property
    def available(self) -> bool:
        return bool(self._rest)


class KiddeOnlineSensor(_RestSensor):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_name = "Online"

    def __init__(self, hass: HomeAssistant, device: KiddeDevice) -> None:
        super().__init__(hass, device)
        self._attr_unique_id = f"ring_kidde_{device.id}_online"

    @property
    def is_on(self) -> bool | None:
        connection = (self._rest.get("alerts") or {}).get("connection")
        return None if connection is None else connection == "online"


class KiddeBatteryProblemSensor(_RestSensor):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Battery problem"

    def __init__(self, hass: HomeAssistant, device: KiddeDevice) -> None:
        super().__init__(hass, device)
        self._attr_unique_id = f"ring_kidde_{device.id}_battery_problem"

    @property
    def is_on(self) -> bool | None:
        value = (self._rest.get("health") or {}).get("battery_error")
        return None if value is None else bool(value)


class KiddeDocSensor(_LiveEntity):
    """End of life / test in progress / malfunction, from the live device doc."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device: KiddeDevice, key: str) -> None:
        super().__init__(entry)
        self._device = device
        self._key = key
        self._attr_unique_id = f"ring_kidde_{device.id}_{key}"
        self._attr_device_info = device_info(device)
        if key == "end_of_life":
            self._attr_name = "End of life"
            self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        elif key == "test":
            self._attr_name = "Test in progress"
            self._attr_device_class = BinarySensorDeviceClass.RUNNING
            self._attr_entity_category = None
        else:
            self._attr_name = "Malfunction"
            self._attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def _doc(self):
        return live_doc_for(self.hass, self._entry, self._device)

    @property
    def _value(self) -> bool | None:
        doc = self._doc
        if self._key == "end_of_life":
            return end_of_life(doc)
        if self._key == "test":
            return test_in_progress(doc)
        codes = malfunctions(doc)
        return None if codes is None else bool(codes)

    @property
    def available(self) -> bool:
        data: KiddeData = self._entry.runtime_data
        client = data.clients.get(self._device.location_id)
        if not (client and client.connected and self._doc is not None):
            return False
        if self._key == "test" and self._test_never_reported:
            return True  # never tested since connect: idle
        return self._value is not None

    @property
    def _test_never_reported(self) -> bool:
        return "pushToTest" not in ((self._doc or {}).get("components") or {})

    @property
    def is_on(self) -> bool | None:
        if self._key == "test" and self._test_never_reported:
            return False
        return self._value

    @property
    def extra_state_attributes(self):
        if self._key == "malfunction":
            return {"codes": malfunctions(self._doc) or []}
        return None
