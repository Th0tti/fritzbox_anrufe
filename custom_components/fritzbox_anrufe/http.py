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

from .const import CALL_MEDIA_URL_BASE, DOMAIN, TAM_MEDIA_URL_BASE

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


class FritzBoxCallMediaView(HomeAssistantView):
    """Stream the recording linked from a call-list entry (since v1.0.3).

    EXPERIMENTAL, same caveat as FritzBoxTamMediaView / see tam.py's module
    docstring: reuses ``FritzTamCoordinator.fetch_audio()`` completely
    unchanged - it only ever reads a ``.Path`` attribute, and
    fritzconnection's call-list ``Call`` objects carry a ``Path`` in the
    same "/download.lua?path=..." format as an answering-machine
    ``TamMessage`` (both ultimately point at the same kind of recording
    file on the box). This has NOT been separately confirmed against real
    hardware - please open a GitHub issue with the resulting HTTP status
    (visible in the Home Assistant log) if a link here 404s/502s while the
    "echte" Anrufbeantworter-Sensor-Wiedergabe still works.
    """

    url = f"{CALL_MEDIA_URL_BASE}/{{entry_id}}/{{call_type}}/{{call_id}}"
    name = "api:fritzbox_anrufe:call_media"
    requires_auth = True

    async def get(
        self, request: web.Request, entry_id: str, call_type: str, call_id: str
    ) -> web.Response:
        """Return the audio bytes for one call-list entry's recording, if any."""
        hass = request.app[KEY_HASS]

        entry = hass.config_entries.async_get_entry(entry_id)
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
        ):
            return web.Response(status=404)

        call_log_coordinator = getattr(entry.runtime_data, "call_log_coordinator", None)
        tam_coordinator = getattr(entry.runtime_data, "tam_coordinator", None)
        if call_log_coordinator is None or tam_coordinator is None:
            return web.Response(status=404)

        call = call_log_coordinator.get_call(call_type, call_id)
        if call is None or not call.Path:
            return web.Response(status=404)

        try:
            audio_bytes, content_type = await hass.async_add_executor_job(
                tam_coordinator.fetch_audio, call
            )
        except RequestException as ex:
            _LOGGER.warning(
                "Fehler beim Abrufen der Anruf-Aufnahme %s/%s: %s",
                call_type,
                call_id,
                ex,
            )
            return web.Response(status=502)

        return web.Response(body=audio_bytes, content_type=content_type)
