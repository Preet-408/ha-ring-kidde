"""Config flow for Ring Kidde — handles login, 2FA, and device detection."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from ring_doorbell import Auth, Ring
from ring_doorbell.exceptions import AuthenticationError, Requires2FAError

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_2FA,
    CONF_TOKEN,
    DOMAIN,
    KIDDE_SMOKE_KINDS,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class RingKiddeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow: login → optional 2FA → detect Kidde devices."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise."""
        self._username: str | None = None
        self._password: str | None = None
        self._auth: Auth | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Step 1 — collect Ring username and password."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            session = async_get_clientsession(self.hass)
            self._auth = Auth(
                USER_AGENT,
                http_client_session=session,
            )

            try:
                token = await self._auth.async_fetch_token(
                    self._username, self._password
                )
                # No 2FA required — proceed to detect devices
                return await self._async_finish(token)

            except Requires2FAError:
                # Ring sent a 2FA code to the user's phone/email
                return await self.async_step_2fa()

            except AuthenticationError:
                errors["base"] = "invalid_auth"

            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Ring login")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_2fa(self, user_input: dict[str, Any] | None = None):
        """Step 2 — collect 2FA code sent by Ring."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                token = await self._auth.async_fetch_token(
                    self._username,
                    self._password,
                    otp_code=user_input[CONF_2FA],
                )
                return await self._async_finish(token)

            except AuthenticationError:
                errors["base"] = "invalid_2fa"

            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Ring 2FA")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="2fa",
            data_schema=vol.Schema({vol.Required(CONF_2FA): str}),
            description_placeholders={
                "username": self._username,
            },
            errors=errors,
        )

    async def _async_finish(self, token: dict) -> config_entries.ConfigFlowResult:
        """Verify we can see at least one Kidde device, then create entry."""
        session = async_get_clientsession(self.hass)

        # Refresh auth with saved token so we can query devices
        auth = Auth(
            USER_AGENT,
            token=token,
            http_client_session=session,
        )
        ring = Ring(auth)

        try:
            await ring.async_update_devices()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to query Ring devices during setup")
            return self.async_abort(reason="cannot_connect")

        # Find Kidde devices in the 'other' family
        other_devices = ring.devices_data.get("other", {})
        kidde_found = [
            d for d in other_devices.values()
            if d.get("kind") in KIDDE_SMOKE_KINDS
        ]

        if not kidde_found:
            _LOGGER.warning(
                "ring_kidde: No Kidde devices found in Ring account. "
                "Detected device kinds in 'other': %s",
                [d.get("kind") for d in other_devices.values()],
            )
            # Still allow setup — devices may appear later
            # return self.async_abort(reason="no_kidde_devices")

        _LOGGER.info(
            "ring_kidde: Found %d Kidde device(s): %s",
            len(kidde_found),
            [d.get("name") for d in kidde_found],
        )

        return self.async_create_entry(
            title=f"Ring Kidde ({self._username})",
            data={
                CONF_USERNAME: self._username,
                CONF_TOKEN: token,
            },
        )
