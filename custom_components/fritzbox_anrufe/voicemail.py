"""Coordinator + audio access for the FRITZ!Box answering machine (TAM).

EXPERIMENTAL - see the module docstring in :mod:`.tam` for details on what
could and could not be verified against real hardware while building this.
"""

from __future__ import annotations

from datetime import timedelta
import logging
import mimetypes

from fritzconnection.core.exceptions import FritzConnectionException, FritzSecurityError
from fritzconnection.core.fritzhttp import FritzHttp
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
        # Only used as a *fallback* sid source for recording downloads
        # (see fetch_audio/_sid_candidates below) - also conveniently
        # provides router_url, the FRITZ!Box's normal web-UI origin
        # (port 80/443), which is needed for every download attempt
        # regardless of which sid ends up working.
        self._http = FritzHttp(fritz_tam.fc)

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

        Tries multiple (sid, origin) candidates in order until one returns
        HTTP 200 - see :meth:`_sid_candidates` and the module docstring in
        ``tam.py`` for why more than one candidate exists. The browser only
        ever needs a valid Home Assistant session to play a recording,
        never FRITZ!Box credentials directly - this whole exchange happens
        server-side.
        """
        if not message.Path:
            raise RequestException("message has no audio path")

        origin = self._http.router_url
        last_status: int | None = None
        tried = 0

        for sid in self._sid_candidates():
            url = self._fritz_tam.build_download_url(message, sid, origin)
            if not url:
                raise RequestException("message has no audio path")
            tried += 1
            try:
                response = self._fritz_tam.fc.session.get(url)
            except (FritzConnectionException, RequestsConnectionError) as ex:
                raise RequestException(
                    f"Anrufbeantworter-Download fehlgeschlagen: {ex}"
                ) from ex
            if response.status_code == 200:
                content_type = (
                    response.headers.get("Content-Type")
                    or mimetypes.guess_type(url)[0]
                    or _DEFAULT_CONTENT_TYPE
                )
                return response.content, content_type
            last_status = response.status_code

        if tried == 0:
            raise RequestException(
                "konnte keine sid für den Anrufbeantworter-Download ermitteln"
            )
        raise RequestException(
            f"Anrufbeantworter-Download fehlgeschlagen (HTTP {last_status})"
            f" nach {tried} Versuch(en) mit unterschiedlichen Sitzungen"
        )

    def _sid_candidates(self):
        """Yield sid candidates to try for a recording download, in order.

        First the sid embedded in a fresh ``GetMessageList`` response (no
        extra login needed), then - only if that candidate exists but the
        caller hasn't already succeeded with it - a full classic-web-UI
        login via ``FritzHttp`` (up to two sids: cached-or-fresh, then
        regenerated once). See the module docstring in ``tam.py`` for why
        both mechanisms are tried rather than picking one.
        """
        try:
            embedded_sid = self._fritz_tam.get_message_list_sid()
        except FritzConnectionException:
            embedded_sid = None
        if embedded_sid:
            yield embedded_sid
        yield from self._http._get_sid()  # noqa: SLF001 - see class docstring
