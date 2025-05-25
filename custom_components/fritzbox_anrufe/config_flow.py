# custom_components/fritzbox_anrufe/config_flow.py

"""Config flow for fritzbox_anrufe."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

import voluptuous as vol
from fritzconnection import FritzConnection
from fritzconnection.core.exceptions import FritzConnectionException, FritzSecurityError
from requests.exceptions import ConnectionError as RequestsConnectionError

from homeassistant.config_entries import ConfigFlow, ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import callback

from .const import (
    DOMAIN,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    CONF_PHONEBOOK,
    CONF_PHONEBOOK_NAME,
    CONF_PREFIXES,
)
from .base import FritzBoxPhonebook

DATA_SCHEMA_USER = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class ConnectResult(StrEnum):
    """Mögliche Ergebnisse beim Verbindungsversuch."""
    INVALID_AUTH = "invalid_auth"
    NO_DEVICES_FOUND = "no_devices_found"
    SUCCESS = "success"


class FritzBoxAnrufeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for fritzbox_anrufe."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._phonebooks: list[dict[str, Any]] | None = None
        self._phonebook_names: dict[str, int] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Schritt 1: FRITZ!Box-Zugangsdaten abfragen."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=DATA_SCHEMA_USER, errors={}
            )

        # Werte speichern
        self._host = user_input[CONF_HOST]
        self._port = user_input[CONF_PORT]
        self._username = user_input[CONF_USERNAME]
        self._password = user_input[CONF_PASSWORD]

        try:
            # Instanziierung im Executor
            fc: FritzConnection = await self.hass.async_add_executor_job(
                lambda: FritzConnection(
                    address=self._host,
                    port=self._port,
                    user=self._username,
                    password=self._password,
                )
            )
            # Ersten API-Call (Telefonbücher) im Executor
            self._phonebooks = await self.hass.async_add_executor_job(
                lambda: fc.call_action("X_AVM-DE_GetPhonebookList")
            )
        except (FritzSecurityError, FritzConnectionException, RequestsConnectionError):
            return self.async_show_form(
                step_id="user",
                data_schema=DATA_SCHEMA_USER,
                errors={"base": ConnectResult.INVALID_AUTH},
            )

        if not self._phonebooks:
            return self.async_abort(reason=ConnectResult.NO_DEVICES_FOUND.value)

        # Weiter zu Schritt 2
        return await self.async_step_phonebook()

    async def async_step_phonebook(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Schritt 2: Auswahl des Telefonbuchs."""
        if self._phonebook_names is None:
            self._phonebook_names = {
                pb["NewPhonebookName"]: int(pb["NewPhonebookID"])
                for pb in self._phonebooks  # type: ignore[union-attr]
            }

        if user_input is None or CONF_PHONEBOOK_NAME not in user_input:
            return self.async_show_form(
                step_id="phonebook",
                data_schema=vol.Schema(
                    {vol.Required(CONF_PHONEBOOK_NAME): vol.In(self._phonebook_names)}
                ),
                errors={},
            )

        name = user_input[CONF_PHONEBOOK_NAME]
        pb_id = self._phonebook_names[name]

        await self.async_set_unique_id(f"{self._host}-{pb_id}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=name,
            data={
                CONF_HOST: self._host,
                CONF_PORT: self._port,
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_PHONEBOOK: pb_id,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FritzBoxAnrufeOptionsFlowHandler:
        """Options-Flow für Präfixe."""
        return FritzBoxAnrufeOptionsFlowHandler()


class FritzBoxAnrufeOptionsFlowHandler(OptionsFlow):
    """Handle the options (prefix list)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    @classmethod
    def _are_prefixes_valid(cls, prefixes: str | None) -> bool:
        return bool(prefixes.strip()) if prefixes else prefixes is None

    @classmethod
    def _get_list_of_prefixes(cls, prefixes: str | None) -> list[str] | None:
        if prefixes is None:
            return None
        return [p.strip() for p in prefixes.split(",") if p.strip()]

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PREFIXES,
                    description={"suggested_value": self.config_entry.options.get(CONF_PREFIXES)},
                ): str
            }
        )

        if user_input is None:
            return self.async_show_form(step_id="init", data_schema=schema, errors={})

        prefixes = user_input.get(CONF_PREFIXES)
        if not self._are_prefixes_valid(prefixes):
            return self.async_show_form(
                step_id="init", data_schema=schema, errors={"base": "malformed_prefixes"}
            )

        return self.async_create_entry(
            title="",
            data={CONF_PREFIXES: self._get_list_of_prefixes(prefixes)},
        )
