"""Coordinator + audio access for the FRITZ!Box answering machine (TAM).

EXPERIMENTAL - see the module docstring in :mod:`.tam` for details on what
could and could not be verified against real hardware while building this.
"""

from __future__ import annotations

from datetime import timedelta
import logging
import mimetypes

from fritzconnection.core.exceptions import FritzConnectionException, FritzSecurityError
from requests.exceptions import ConnectionError as RequestsConnectionError, RequestException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .tam import FritzTam, TamMessage

_LOGGER = logging.getLogger(__name__)

TAM_UPDATE_INTERVAL = timedelta(minutes=5)
_DEFAULT_CONTENT_TYPE = "audio/wav"


class FritzTamCoordinator(DataUpdateCoordinator[list[TamMessage]]):
    """Coordinator that periodically fetches the FRITZ!Box answering-machine list.

    Also doubles as the (blocking, executor-job-only) audio fetcher for the
    HTTP proxy view in ``http.py``, since it already holds the
    authenticated :class:`~.tam.FritzTam`/``FritzConnection`` reference.
    """

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, fritz_tam: FritzTam
    ) -> None:
        """Initialize the TAM coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="fritzbox_anrufe tam",
            update_interval=TAM_UPDATE_INTERVAL,
        )
        self.config_entry = config_entry
        self._fritz_tam = fritz_tam

    async def _async_update_data(self) -> list[TamMessage]:
        """Fetch the current answering-machine messages (executor job)."""
        try:
            return await self.hass.async_add_executor_job(self._fritz_tam.get_messages)
        except FritzSecurityError as ex:
            raise UpdateFailed(
                "Dem FRITZ!Box-Konto fehlt die Berechtigung 'Sprachnachrichten,"
                " Faxnachrichten, FRITZ!App Fon und Anrufliste' für den Zugriff"
                f" auf den Anrufbeantworter: {ex}"
            ) from ex
        except (FritzConnectionException, RequestsConnectionError) as ex:
            raise UpdateFailed(
                f"Fehler beim Abrufen der Anrufbeantworter-Nachrichten: {ex}"
            ) from ex

    def get_message(self, message_id: str) -> TamMessage | None:
        """Look up one currently-known message by its raw ``Index`` string."""
        for message in self.data or []:
            if message.Index == message_id:
                return message
        return None

    def fetch_audio(self, message: TamMessage) -> tuple[bytes, str]:
        """Download one message's audio recording. BLOCKING - run in executor.

        See :meth:`.tam.FritzTam.get_download_url` for how the actual
        download URL (and its sid) is built - this is a plain authenticated
        GET against that URL, so the browser only ever needs a valid Home
        Assistant session to play a recording, never FRITZ!Box credentials
        directly.
        """
        try:
            url = self._fritz_tam.get_download_url(message)
        except FritzConnectionException as ex:
            raise RequestException(
                f"FRITZ!Box-Anfrage für Anrufbeantworter-Download"
                f" fehlgeschlagen: {ex}"
            ) from ex

        if not url:
            raise RequestException(
                "konnte keine Download-URL für die Anrufbeantworter-"
                "Nachricht ermitteln"
            )

        response = self._fritz_tam.fc.session.get(url)
        response.raise_for_status()

        content_type = (
            response.headers.get("Content-Type")
            or mimetypes.guess_type(url)[0]
            or _DEFAULT_CONTENT_TYPE
        )
        return response.content, content_type
