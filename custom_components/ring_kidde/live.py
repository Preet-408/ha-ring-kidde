"""Live alarm state for Kidde-on-Ring detectors.

Ring pushes smoke/CO alarm state over its "clap" websocket, not over the REST
device list that Home Assistant's Ring integration polls. This mirrors what
ring-client-api's Location does (ticket -> wss://<host>/ws -> DeviceInfoDocGetList),
including the fix for accounts whose only "hub" is a Kidde alarm: Kidde assets
in the ticket are accepted instead of being filtered out.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
import json
import logging
import time
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONNECT_TIMEOUT_SECONDS,
    DEVICE_LIST_MSG,
    RECONNECT_MAX_SECONDS,
    RECONNECT_MIN_SECONDS,
    LIST_RESPONSE_TIMEOUT_SECONDS,
    REFRESH_LIST_SECONDS,
    TICKET_PATH,
)

_LOGGER = logging.getLogger(__name__)

APP_API_URI = "https://prd-api-us.prd.rings.solutions"


def _flatten(item: dict[str, Any]) -> dict[str, Any]:
    """general.v2 + device.v1, like ring-client-api's flattenDeviceData."""
    general = (item.get("general") or {}).get("v2") or {}
    device = (item.get("device") or {}).get("v1") or {}
    return {**general, **device}


def _deep_merge(base: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial update into the stored doc."""
    out = dict(base)
    for key, value in new.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def alarm_state(doc: dict[str, Any] | None, key: str) -> bool | None:
    """'active' -> True, 'inactive' -> False, anything else -> None (unknown).

    Only an explicit 'active' turns an alarm on, so a missing or unexpected
    value never shows as a false alarm.
    """
    if not doc:
        return None
    comp = (doc.get("components") or {}).get(f"alarm.{key}")
    if not isinstance(comp, dict):
        comp = doc.get(key) if isinstance(doc.get(key), dict) else {}
    status = comp.get("alarmStatus")
    if status == "active":
        return True
    if status == "inactive":
        return False
    return None


class KiddeLiveClient:
    """One websocket per Ring location that has Kidde alarms."""

    def __init__(
        self,
        hass: HomeAssistant,
        get_api: Callable[[], Any],
        location_id: str,
        on_change: Callable[[], None],
    ) -> None:
        self._hass = hass
        self._get_api = get_api
        self.location_id = location_id
        self._on_change = on_change
        self.docs: dict[str, dict[str, Any]] = {}  # zid -> merged doc
        self.doc_src: dict[str, str] = {}  # zid -> asset uuid it came from
        self.assets: list[dict[str, Any]] = []
        self.connected = False
        self.last_error: str | None = None
        self.samples: deque[dict[str, Any]] = deque(maxlen=25)
        self._seq = 1
        self._received: set[str] = set()  # assets that answered the current list request
        self._awaiting_since: float | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task | None = None
        self._stopping = False

    @callback
    def start(self) -> None:
        self._task = self._hass.async_create_background_task(
            self._run(), f"ring_kidde_live_{self.location_id}"
        )

    async def stop(self) -> None:
        self._stopping = True
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def _set_connected(self, value: bool) -> None:
        if self.connected != value:
            self.connected = value
            self._on_change()

    async def _run(self) -> None:
        delay = RECONNECT_MIN_SECONDS
        while not self._stopping:
            try:
                got_list = await self._connect_once()
                if got_list:
                    delay = RECONNECT_MIN_SECONDS
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - keep the loop alive
                self.last_error = _safe_error(err)
                _LOGGER.warning("Kidde live link error (%s), retrying in %ss", self.last_error, delay)
            self._set_connected(False)
            if self._stopping:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_SECONDS)

    async def _fetch_ticket(self) -> dict[str, Any]:
        api = self._get_api()
        if api is None:
            raise RuntimeError("Ring integration is not loaded")
        resp = await api.async_query(
            TICKET_PATH,
            extra_params={
                "locationID": self.location_id,
                "enableExtendedEmergencyCellUsage": "true",
                "requestedTransport": "ws",
            },
            base_uri=APP_API_URI,
        )
        return resp.json()

    async def _send_list_requests(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self._received.clear()
        self._awaiting_since = time.monotonic()
        for asset in self.assets:
            msg = {"msg": DEVICE_LIST_MSG, "dst": asset["uuid"], "seq": self._seq}
            self._seq += 1
            await ws.send_str(json.dumps({"channel": "message", "msg": msg}))

    async def _connect_once(self) -> bool:
        ticket = await self._fetch_ticket()
        all_assets = ticket.get("assets") or []
        # Ticket assets use the bare "sensor_bluejay" kind (devices use sensor_bluejay_<x>).
        self.assets = [
            a for a in all_assets if str(a.get("kind") or "").startswith("sensor_bluejay") and a.get("uuid")
        ]
        if not self.assets:
            raise RuntimeError(
                "no Kidde assets in Ring ticket (kinds: "
                f"{sorted({str(a.get('kind')) for a in all_assets})})"
            )
        session = async_get_clientsession(self._hass)
        ws = await asyncio.wait_for(
            session.ws_connect(
                f"wss://{ticket['host']}/ws",
                params={"authcode": ticket["ticket"], "ack": "false"},
                heartbeat=30,
            ),
            CONNECT_TIMEOUT_SECONDS,
        )
        self._ws = ws
        got_list = False
        # Fresh connection: forget everything, so a stale "active" can never resurface.
        self.docs.clear()
        self.doc_src.clear()
        self._on_change()
        try:
            await self._send_list_requests(ws)
            next_refresh = time.monotonic() + REFRESH_LIST_SECONDS
            while not self._stopping:
                now = time.monotonic()
                if self._awaiting_since is not None and now - self._awaiting_since > LIST_RESPONSE_TIMEOUT_SECONDS:
                    self.last_error = "Ring did not answer the device list request"
                    break
                if now >= next_refresh:
                    await self._send_list_requests(ws)
                    next_refresh = now + REFRESH_LIST_SECONDS
                    continue
                wait = min(next_refresh - now, 5.0)
                try:
                    message = await ws.receive(timeout=wait)
                except TimeoutError:
                    continue
                if message.type == aiohttp.WSMsgType.TEXT:
                    result = self._handle(message.data)
                    if result == "list":
                        got_list = True
                        self.last_error = None
                    elif result == "reconnect":
                        break
                elif message.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.ERROR,
                ):
                    self.last_error = f"socket closed ({message.type.name})"
                    break
        finally:
            self._ws = None
            if not ws.closed:
                await ws.close()
        return got_list

    def _handle(self, raw: str) -> str | None:
        try:
            payload = json.loads(raw)
        except ValueError:
            _LOGGER.debug("Kidde live: non-JSON message ignored")
            return None
        channel = payload.get("channel")
        msg = payload.get("msg") or {}
        if not isinstance(msg, dict):
            return None
        self.samples.append(
            {
                "channel": channel,
                "msg": msg.get("msg"),
                "datatype": msg.get("datatype"),
                "src": msg.get("src"),
                "body": msg.get("body"),
            }
        )
        if msg.get("datatype") == "HubDisconnectionEventType":
            return "reconnect"

        is_list = msg.get("msg") == DEVICE_LIST_MSG
        is_update = channel == "DataUpdate" and msg.get("datatype") == "DeviceInfoDocType"
        body = msg.get("body")
        if not (is_list or is_update) or not isinstance(body, list):
            return None

        changed = False
        for item in body:
            if not isinstance(item, dict):
                continue
            flat = _flatten(item)
            zid = flat.get("zid")
            if not zid:
                continue
            self.docs[zid] = _deep_merge(self.docs.get(zid, {}), flat)
            if msg.get("src"):
                self.doc_src[zid] = msg["src"]
            changed = True
        if is_list and msg.get("src"):
            self._received.add(msg["src"])
            if all(a["uuid"] in self._received for a in self.assets):
                self._awaiting_since = None
                self._set_connected(True)
        if changed:
            _LOGGER.debug("Kidde live: %s docs updated (%s)", len(body), "list" if is_list else "update")
            self._on_change()
        return "list" if is_list else None


def _safe_error(err: Exception) -> str:
    """Error text without URLs (aiohttp handshake errors include the authcode)."""
    status = getattr(err, "status", None)
    name = type(err).__name__
    if isinstance(err, RuntimeError) and "Kidde assets" in str(err):
        return str(err)
    return f"{name} (HTTP {status})" if status else name


def end_of_life(doc: dict[str, Any] | None) -> bool | None:
    """End-of-life alarm or warning active (alarms expire after ~10 years)."""
    comp = ((doc or {}).get("components") or {}).get("alarm.end-of-life")
    if not isinstance(comp, dict):
        return None
    states = {comp.get("alarmStatus"), comp.get("warningStatus")} - {None}
    if "active" in states:
        return True
    if states and states <= {"inactive"}:
        return False
    return None


def test_in_progress(doc: dict[str, Any] | None) -> bool | None:
    """Push-to-test button: 'active' while a test runs."""
    comp = ((doc or {}).get("components") or {}).get("pushToTest")
    status = comp.get("status") if isinstance(comp, dict) else None
    return {"active": True, "inactive": False}.get(status)


def malfunctions(doc: dict[str, Any] | None) -> list[str] | None:
    """Current malfunction codes (e.g. PTT_BUTTON_STUCK); [] when none, None when unknown."""
    if not doc:
        return None
    components = doc.get("components") or {}
    if "malfunctions" not in components:
        return []  # never reported: nothing wrong
    comp = components["malfunctions"]
    if not isinstance(comp, dict) or "current" not in comp:
        return None
    current = comp["current"]
    if current is None:
        return []  # observed: cleared
    if isinstance(current, list):
        return [str(c) for c in current]
    return None
