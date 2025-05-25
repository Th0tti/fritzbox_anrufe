"""Config flow for fritzbox_anrufe."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, cast

from fritzconnection import FritzConnection
from fritzconnection.core.exceptions import FritzConnectionException, FritzSecurityError
from requests.exceptions import ConnectionError as RequestsConnectionError
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback

from .const import (
    CONF_PHONEBOOK,
    CONF_PHONEBOOK_NAME,
    CONF_PREFIXES,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    DEFAULT_PHONEBOOK,
    DEFAULT_NAME,
    DOMAIN,
)

DATA_SCHEMA_USER = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

class ConnectResult(StrEnum):
    """FritzBoxPhonebook connection result."""

    INVALID_AUTH = "invalid_auth"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    MALFORMED_PREFIXES = "malformed_prefixes"
    NO_DEVICES_FOUND = "no_devices_found"
    SUCCESS = "success"

@callback
def configured_instances(hass: HomeAssistant) -> list[str]:
    """Return a list of configured fritzbox_anrufe instances."""
    return []

class FritzBoxCallMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a fritzbox_anrufe config flow."""

    VERSION = 1
    _entry: ConfigEntry

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=DATA_SCHEMA_USER, errors={}
            )

        try:
            fc = FritzConnection(
                address=user_input[CONF_HOST],
                port=user_input[CONF_PORT],
                user=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
            )
            phonebooks = await hass.async_add_executor_job(fc.call_action, "X_AVM-DE_GetPhonebookList")
        except (FritzSecurityError, FritzConnectionException, RequestsConnectionError):
            return self.async_show_form(
                step_id="user", data_schema=DATA_SCHEMA_USER, errors={"base": ConnectResult.INVALID_AUTH}
            )

        if not phonebooks:
            return self.async_abort(reason=ConnectResult.NO_DEVICES_FOUND.value)

        return self.async_step_phonebook({"phonebooks": phonebooks})

    # … hier folgt der Rest der Schritte, unverändert übernehmen …
