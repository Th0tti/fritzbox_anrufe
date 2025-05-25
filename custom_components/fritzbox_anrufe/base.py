"""Base class for fritzbox_anrufe entities."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
import logging
import re

from fritzconnection.lib.fritzphonebook import FritzPhonebook

from homeassistant.util import Throttle

from .const import CONF_PHONEBOOK, CONF_PREFIXES, DOMAIN

_LOGGER = logging.getLogger(__name__)

THROTTLE_INTERVAL = timedelta(seconds=30)

@dataclass
class Contact:
    """Dataclass to hold a contact."""
    name: str
    number: str
    vip: bool = False

class FritzBoxPhonebook:
    """Connect to Fritz!Box and fetch the phonebook."""

    def __init__(self, hass, data, options, entry_id):
        self.hass = hass
        self.host = data[CONF_HOST]
        self.port = data[CONF_PORT]
        self.username = data[CONF_USERNAME]
        self.password = data[CONF_PASSWORD]
        self.phonebook_id = data[CONF_PHONEBOOK]
        self.prefixes = options.get(CONF_PREFIXES)
        self._entry_id = entry_id
        self._phonebook = FritzPhonebook(address=self.host, port=self.port, user=self.username, password=self.password)
        self.number_dict: dict[str, Contact] = {}
        self._last_update = None

    @Throttle(THROTTLE_INTERVAL)
    async def async_setup(self) -> None:
        """Fetch phonebook and build lookup dict."""
        try:
            numbers = await self.hass.async_add_executor_job(
                self._phonebook.call_action,
                "X_AVM-DE_GetPhonebook",
                {"NewPhonebookID": self.phonebook_id},
            )
            # … parse XML, fülle self.number_dict …
        except Exception as err:
            _LOGGER.error("Fehler beim Laden der Telefonbuchdaten: %s", err)

    def number_to_contact(self, number: str) -> Contact:
        """Map a raw number to a Contact, anhand Prefixes oder geladener Dict."""
        unknown_contact = Contact(name=UNKNOWN_NAME, number=number)
        with suppress(KeyError):
            return self.number_dict[number]

        if not self.prefixes:
            return unknown_contact

        for prefix in self.prefixes:
            with suppress(KeyError):
                return self.number_dict[prefix + number]
            with suppress(KeyError):
                return self.number_dict[prefix + number.lstrip("0")]

        return unknown_contact
