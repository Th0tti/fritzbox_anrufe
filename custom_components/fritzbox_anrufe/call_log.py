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

Important API constraint
-------------------------
``fritzconnection``/the FRITZ!Box TR-064 call list can only be limited by
ONE shared parameter for the *combined* (all call types mixed) download -
either "last N days" or "last N entries overall", never per call type. So a
"last 10 incoming calls" request cannot be sent to the box directly: asking
for the last 10 entries overall might return, say, 9 outgoing and 1
incoming call if the account mostly dials out.

To still offer independent per-sensor limits (as configured via
``conf_call_log_count``/``conf_call_log_days``), this coordinator always
downloads one generous, shared window - the last
:data:`~.const.SHARED_CALL_LOG_FETCH_DAYS` days, combined across all call
types - once per polling cycle, and then applies each sensor's own count/
days limit *client-side*, after splitting the shared download by type. The
practical consequence: if a sensor is configured for "days" mode, that
sensor can never see further back than the shared fetch window (90 days by
default); a "count" mode sensor will show fewer than its configured count
if there simply weren't that many calls of that type within the shared
window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

from fritzconnection.core.exceptions import FritzConnectionException, FritzSecurityError
from fritzconnection.lib.fritzcall import (
    MISSED_CALL_TYPE,
    OUT_CALL_TYPE,
    RECEIVED_CALL_TYPE,
    Call,
    FritzCall,
)
from requests.exceptions import ConnectionError as RequestsConnectionError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CALL_LOG_LIMIT_DAYS,
    CALL_TYPE_INCOMING,
    CALL_TYPE_MISSED,
    CALL_TYPE_OUTGOING,
    CALL_TYPES,
    DEFAULT_CALL_LOG_COUNT,
    DEFAULT_CALL_LOG_DAYS,
    DEFAULT_CALL_LOG_LIMIT_TYPE,
    SHARED_CALL_LOG_FETCH_DAYS,
    conf_call_log_count,
    conf_call_log_days,
    conf_call_log_limit_type,
)

_LOGGER = logging.getLogger(__name__)

CALL_LOG_UPDATE_INTERVAL = timedelta(minutes=5)

# Maps our internal call-type slugs to fritzconnection's numeric call types.
_CALL_TYPE_CODES: dict[str, int] = {
    CALL_TYPE_INCOMING: RECEIVED_CALL_TYPE,
    CALL_TYPE_MISSED: MISSED_CALL_TYPE,
    CALL_TYPE_OUTGOING: OUT_CALL_TYPE,
}


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

    def _limit_for(self, call_type: str) -> tuple[str, int]:
        """Return (limit_type, value) for one call-list sensor's own option."""
        options = self.config_entry.options
        limit_type = options.get(
            conf_call_log_limit_type(call_type), DEFAULT_CALL_LOG_LIMIT_TYPE
        )
        if limit_type == CALL_LOG_LIMIT_DAYS:
            return limit_type, options.get(conf_call_log_days(call_type), DEFAULT_CALL_LOG_DAYS)
        return limit_type, options.get(conf_call_log_count(call_type), DEFAULT_CALL_LOG_COUNT)

    def _apply_limit(self, calls: list[Call], call_type: str) -> list[Call]:
        """Truncate an already type-filtered call list to its own setting."""
        limit_type, value = self._limit_for(call_type)
        if limit_type == CALL_LOG_LIMIT_DAYS:
            cutoff = datetime.now() - timedelta(days=value)
            return [call for call in calls if isinstance(call.date, datetime) and call.date >= cutoff]
        return calls[:value]

    def _fetch_calls(self) -> CallLogData:
        """Download the shared call list once and split/limit it per type.

        Only the first ``get_calls()`` passes ``update=True`` so the raw,
        combined call list is downloaded from the FRITZ!Box exactly once per
        polling cycle; the other two calls filter the already-downloaded,
        cached data by type.
        """
        call_types = list(CALL_TYPES)
        first_type = call_types[0]
        calls_by_type: dict[str, list[Call]] = {}

        first_raw = self._fritz_call.get_calls(
            calltype=_CALL_TYPE_CODES[first_type],
            update=True,
            days=SHARED_CALL_LOG_FETCH_DAYS,
        )
        calls_by_type[first_type] = self._apply_limit(first_raw, first_type)

        for call_type in call_types[1:]:
            raw = self._fritz_call.get_calls(
                calltype=_CALL_TYPE_CODES[call_type], update=False
            )
            calls_by_type[call_type] = self._apply_limit(raw, call_type)

        return CallLogData(calls_by_type=calls_by_type)

    async def _async_update_data(self) -> CallLogData:
        """Fetch the current call lists from the FRITZ!Box (executor job)."""
        try:
            return await self.hass.async_add_executor_job(self._fetch_calls)
        except FritzSecurityError as ex:
            raise UpdateFailed(
                "Dem FRITZ!Box-Konto fehlt die Berechtigung 'Sprachnachrichten,"
                " Faxnachrichten, FRITZ!App Fon und Anrufliste' für den Abruf"
                f" der Anrufliste: {ex}"
            ) from ex
        except (FritzConnectionException, RequestsConnectionError) as ex:
            raise UpdateFailed(f"Fehler beim Abrufen der FRITZ!Box-Anrufliste: {ex}") from ex
