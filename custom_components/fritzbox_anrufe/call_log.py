"""Coordinator to poll the FRITZ!Box call list (incoming/outgoing/missed).

Unlike the call monitor (TCP port 1012), which only streams live call
*events* while Home Assistant is running, the historical call list is not
available via the call monitor. It has to be fetched from the FRITZ!Box via
the TR-064 service ``X_AVM-DE_OnTel`` ("GetCallList"), which is exactly what
:class:`fritzconnection.lib.fritzcall.FritzCall` wraps. The FRITZ!Box user
account configured for this integration needs the account permission
"Sprachnachrichten, Faxnachrichten, FRITZ!App Fon und Anrufliste" for this
to work; otherwise the call list sensors will show as unavailable while the
existing call monitor sensor keeps working normally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging

from fritzconnection.core.exceptions import FritzConnectionException, FritzSecurityError
from fritzconnection.lib.fritzcall import Call, FritzCall
from requests.exceptions import ConnectionError as RequestsConnectionError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CALL_LOG_LIMIT_COUNT,
    CALL_TYPE_INCOMING,
    CALL_TYPE_MISSED,
    CALL_TYPE_OUTGOING,
    CONF_CALL_LOG_COUNT,
    CONF_CALL_LOG_DAYS,
    CONF_CALL_LOG_LIMIT_TYPE,
    DEFAULT_CALL_LOG_COUNT,
    DEFAULT_CALL_LOG_LIMIT_TYPE,
)

_LOGGER = logging.getLogger(__name__)

CALL_LOG_UPDATE_INTERVAL = timedelta(minutes=5)


@dataclass
class CallLogData:
    """Container bundling the three call lists for one polling cycle."""

    calls_by_type: dict[str, list[Call]] = field(default_factory=dict)

    def calls(self, call_type: str) -> list[Call]:
        """Return the calls of the given type ("eingehend"/"ausgehend"/"verpasst")."""
        return self.calls_by_type.get(call_type, [])


class FritzCallLogCoordinator(DataUpdateCoordinator[CallLogData]):
    """Coordinator that periodically fetches the FRITZ!Box call list via TR-064."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        fritz_call: FritzCall,
    ) -> None:
        """Initialize the call log coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="fritzbox_anrufe call log",
            update_interval=CALL_LOG_UPDATE_INTERVAL,
        )
        self.config_entry = config_entry
        self._fritz_call = fritz_call

    def _limit_kwargs(self) -> dict[str, int]:
        """Translate the configured options into get_*_calls() keyword args."""
        options = self.config_entry.options
        limit_type = options.get(CONF_CALL_LOG_LIMIT_TYPE, DEFAULT_CALL_LOG_LIMIT_TYPE)
        if limit_type == CALL_LOG_LIMIT_COUNT:
            return {"num": options.get(CONF_CALL_LOG_COUNT, DEFAULT_CALL_LOG_COUNT)}
        days = options.get(CONF_CALL_LOG_DAYS)
        return {"days": days} if days else {}

    def _fetch_calls(self, kwargs: dict[str, int]) -> CallLogData:
        """Fetch all three call lists, reusing one call-list download.

        Only the first call passes ``update=True`` so the raw call list is
        downloaded from the FRITZ!Box exactly once per polling cycle; the
        other two calls filter the already-downloaded, cached data.
        """
        received = self._fritz_call.get_received_calls(update=True, **kwargs)
        missed = self._fritz_call.get_missed_calls(update=False, **kwargs)
        outgoing = self._fritz_call.get_out_calls(update=False, **kwargs)
        return CallLogData(
            calls_by_type={
                CALL_TYPE_INCOMING: received,
                CALL_TYPE_MISSED: missed,
                CALL_TYPE_OUTGOING: outgoing,
            }
        )

    async def _async_update_data(self) -> CallLogData:
        """Fetch the current call lists from the FRITZ!Box (executor job)."""
        kwargs = self._limit_kwargs()
        try:
            return await self.hass.async_add_executor_job(self._fetch_calls, kwargs)
        except FritzSecurityError as ex:
            raise UpdateFailed(
                "Dem FRITZ!Box-Konto fehlt die Berechtigung 'Sprachnachrichten,"
                " Faxnachrichten, FRITZ!App Fon und Anrufliste' für den Abruf"
                f" der Anrufliste: {ex}"
            ) from ex
        except (FritzConnectionException, RequestsConnectionError) as ex:
            raise UpdateFailed(f"Fehler beim Abrufen der FRITZ!Box-Anrufliste: {ex}") from ex
