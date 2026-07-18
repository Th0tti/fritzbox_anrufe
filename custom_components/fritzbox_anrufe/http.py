"""Authenticated proxy view for FRITZ!Box answering-machine (TAM) audio.

EXPERIMENTAL - see :mod:`.tam`. The FRITZ!Box audio recording itself
requires a FRITZ!Box-session-authenticated request (not a Home Assistant
one), so it cannot simply be linked to directly from a dashboard. This
view fetches the audio bytes server-side, using the FRITZ!Box session the
integration already opened, and streams them to the browser - the browser
only ever needs to be authenticated with Home Assistant
(``requires_auth = True``).
"""

from __future__ import annotations

import logging

from aiohttp import web
from requests.exceptions import RequestException

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.config_entries import ConfigEntryState

from .const import DOMAIN, TAM_MEDIA_URL_BASE

_LOGGER = logging.getLogger(__name__)


class FritzBoxTamMediaView(HomeAssistantView):
    """Stream one answering-machine message's audio recording."""

    url = f"{TAM_MEDIA_URL_BASE}/{{entry_id}}/{{message_id}}"
    name = "api:fritzbox_anrufe:tam_media"
    requires_auth = True

    async def get(
        self, request: web.Request, entry_id: str, message_id: str
    ) -> web.Response:
        """Return the audio bytes for one TAM message, if available."""
        hass = request.app[KEY_HASS]

        entry = hass.config_entries.async_get_entry(entry_id)
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
        ):
            return web.Response(status=404)

        tam_coordinator = getattr(entry.runtime_data, "tam_coordinator", None)
        if tam_coordinator is None:
            return web.Response(status=404)

        message = tam_coordinator.get_message(message_id)
        if message is None or not message.Path:
            return web.Response(status=404)

        try:
            audio_bytes, content_type = await hass.async_add_executor_job(
                tam_coordinator.fetch_audio, message
            )
        except RequestException as ex:
            _LOGGER.warning(
                "Fehler beim Abrufen der Anrufbeantworter-Nachricht %s: %s",
                message_id,
                ex,
            )
            return web.Response(status=502)

        return web.Response(body=audio_bytes, content_type=content_type)
