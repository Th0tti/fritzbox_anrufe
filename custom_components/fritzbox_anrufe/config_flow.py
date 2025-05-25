"""Config flow for fritzbox_anrufe."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, cast

import voluptuous as vol
from fritzconnection import FritzConnection
from fritzconnection.core.exceptions import FritzConnectionException, FritzSecurityError
from requests.exceptions import ConnectionError as RequestsConnectionError

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback

from .base import FritzBoxPhonebook
from .const import (
    CONF_PHONEBOOK,
    CONF_PHONEBOOK_NAME,
    CONF_PREFIXES,
    DEFAULT_HOST,
    DEFAULT_PHONEBOOK,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    DOMAIN,
    FRITZ_ATTR_NAME,
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
    """Result of trying to connect to the Fritz!Box."""
    INVALID_AUTH = "invalid_auth"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    NO_DEVICES_FOUND = "no_devices_found"
    SUCCESS = "success"


class FritzBoxAnrufeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for fritzbox_anrufe."""

    VERSION = 1
    _phonebook_names: dict[str, int] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Eingabe von Host/Port/Benutzer/Passwort."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=DATA_SCHEMA_USER,
                errors={},
            )

        # Werte merken
        self._host = user_input[CONF_HOST]
        self._port = user_input[CONF_PORT]
        self._username = user_input[CONF_USERNAME]
        self._password = user_input[CONF_PASSWORD]

        # **WICHTIG**: Instanziierung und erster Call im Executor, damit kein Blocking im Event-Loop passiert
        try:
            # FritzConnection erstellen
            fc: FritzConnection = await self.hass.async_add_executor_job(
                FritzConnection,
                {"address": self._host, "port": self._port, "user": self._username, "password": self._password},
            )
            # Phonebook-Liste abrufen
            phonebooks = await self.hass.async_add_executor_job(
                fc.call_action, "X_AVM-DE_GetPhonebookList"
            )
        except (FritzSecurityError, FritzConnectionException, RequestsConnectionError):
            return self.async_show_form(
                step_id="user",
                data_schema=DATA_SCHEMA_USER,
                errors={"base": ConnectResult.INVALID_AUTH},
            )

        if not phonebooks:
            return self.async_abort(reason=ConnectResult.NO_DEVICES_FOUND.value)

        # Liste für nächsten Schritt vorhalten
        return await self.async_step_phonebook({"phonebooks": phonebooks})

    async def async_step_phonebook(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Auswahl des Telefonbuchs."""
        if self._phonebook_names is None:
            # Mapping Name -> ID
            self._phonebook_names = {
                pb["NewPhonebookName"]: int(pb["NewPhonebookID"])
                for pb in user_input["phonebooks"]
            }

        if user_input is None or CONF_PHONEBOOK_NAME not in user_input:
            return self.async_show_form(
                step_id="phonebook",
                data_schema=vol.Schema(
                    {vol.Required(CONF_PHONEBOOK_NAME): vol.In(self._phonebook_names)}
                ),
                errors={},
            )

        # Ausgewähltes Telefonbuch übernehmen
        self._phonebook_name = user_input[CONF_PHONEBOOK_NAME]
        self._phonebook_id = self._phonebook_names[self._phonebook_name]

        await self.async_set_unique_id(f"{self._host}-{self._phonebook_id}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=self._phonebook_name,
            data={
                CONF_HOST: self._host,
                CONF_PORT: self._port,
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_PHONEBOOK: self._phonebook_id,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FritzBoxAnrufeOptionsFlowHandler:
        """Handle options (Prefix-Konfiguration)."""
        return FritzBoxAnrufeOptionsFlowHandler()
