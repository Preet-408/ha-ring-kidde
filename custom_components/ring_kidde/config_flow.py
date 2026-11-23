"""Config flow: one confirm step. Uses the Ring integration's login, no password here."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState, ConfigFlow, ConfigFlowResult

from . import find_kidde_devices
from .const import DOMAIN


class RingKiddeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not any(
            e.state is ConfigEntryState.LOADED for e in self.hass.config_entries.async_entries("ring")
        ):
            return self.async_abort(reason="ring_not_loaded")
        devices = find_kidde_devices(self.hass)
        if not devices:
            return self.async_abort(reason="no_kidde_devices")
        if user_input is not None:
            return self.async_create_entry(title="Ring Kidde", data={})
        return self.async_show_form(
            step_id="user",
            description_placeholders={"devices": ", ".join(d.name for d in devices)},
        )
