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
    ALL_CALL_TYPES,
    MISSED_CALL_TYPE,
    OUT_CALL_TYPE,
    RECEIVED_CALL_TYPE,
    REJECTED_CALL_TYPE,
    Call,
    FritzCall,
)
from requests.exceptions import ConnectionError as RequestsConnectionError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CALL_LOG_LIMIT_DAYS,
    CALL_OUTCOME_ANSWERED,
    CALL_OUTCOME_CONNECTED,
    CALL_OUTCOME_NOT_CONNECTED,
    CALL_OUTCOME_UNREACHED,
    CALL_OUTCOME_VOICEMAIL,
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


def _classify_call(call: Call) -> tuple[str | None, str | None]:
    """Return (bucket, outcome) for one raw Call - see the module docstring.

    ``bucket`` is one of CALL_TYPES ("eingehend"/"ausgehend"/"verpasst"), or
    None for the two transient "call in progress" raw types (not relevant
    for a *history* list - the live call-monitor sensor already covers
    that), which are simply dropped.

    ``outcome`` (see const.py) is a finer-grained classification *within*
    a bucket, used by the dashboard card's optional "Weiterverarbeitung"
    row (since v1.0.3):

    - REJECTED_CALL_TYPE (10) covers calls the FRITZ!Box itself intercepted
      before they rang through to a person - e.g. a phonebook/blocklist
      rule, or a contact configured to go straight to the answering
      machine. Confirmed necessary by a real-world report: such a call did
      not appear under "Verpasste Anrufe" at all before this was added - it
      was simply invisible to all three sensors.
    - RECEIVED_CALL_TYPE (1) covers BOTH a call answered by a person AND a
      call that went to the answering machine and recorded a message - AVM
      groups both under its own "incoming calls" filter and only tells them
      apart visually (a different icon) based on whether ``Path`` (the
      recording, if any) is set. Since v1.0.3, this integration follows
      that same signal to reclassify "went to the answering machine" calls
      as CALL_TYPE_MISSED instead of CALL_TYPE_INCOMING - "eingehend"
      therefore only ever contains genuinely person-answered calls.
    - Within CALL_TYPE_MISSED, whether a message was actually recorded
      (``Path`` set) is again determined via CALL_OUTCOME_VOICEMAIL vs.
      CALL_OUTCOME_UNREACHED. The FRITZ!Box call list does not reliably
      expose a *further* distinction between "caller hung up before the
      answering machine picked up" and "reached the answering machine's
      greeting but left no message" - both fall under
      CALL_OUTCOME_UNREACHED for now. See the module-level
      ``_log_raw_call_for_diagnostics`` debug logging below, added to
      gather real examples of both cases before attempting a finer split.
    - For OUT_CALL_TYPE (3), only connection duration is evaluated: the
      FRITZ!Box call list does not expose a dedicated "busy" signal
      distinguishable from a plain unanswered outgoing call - both show as
      zero duration. See README, Fehlerbehebung.
    """
    has_recording = bool(call.Path)

    if call.type == RECEIVED_CALL_TYPE:
        if has_recording:
            return CALL_TYPE_MISSED, CALL_OUTCOME_VOICEMAIL
        return CALL_TYPE_INCOMING, CALL_OUTCOME_ANSWERED

    if call.type in (MISSED_CALL_TYPE, REJECTED_CALL_TYPE):
        if has_recording:
            return CALL_TYPE_MISSED, CALL_OUTCOME_VOICEMAIL
        return CALL_TYPE_MISSED, CALL_OUTCOME_UNREACHED

    if call.type == OUT_CALL_TYPE:
        outcome = CALL_OUTCOME_CONNECTED if call.duration else CALL_OUTCOME_NOT_CONNECTED
        return CALL_TYPE_OUTGOING, outcome

    # ACTIVE_RECEIVED_CALL_TYPE (9) / ACTIVE_OUT_CALL_TYPE (11) - ignored.
    return None, None


def _log_raw_call_for_diagnostics(call: Call, bucket: str | None, outcome: str | None) -> None:
    """Temporary DEBUG log of one call's raw fields alongside our classification.

    Added in v1.0.3 specifically to collect real-world examples for the
    still-unconfirmed distinction mentioned in ``_classify_call`` above
    (hung up before the answering machine vs. reached it without leaving a
    message). Enable debug logging for ``custom_components.fritzbox_anrufe``
    (Einstellungen -> Geräte & Dienste -> FRITZ!Box Anrufe -> Info-Symbol
    aktivieren, oder in configuration.yaml unter ``logger: logs:``) and
    reproduce a specific scenario to see the exact raw values here.
    """
    _LOGGER.debug(
        "Anrufliste: Id=%s Type=%s Path=%r Duration=%r Date=%s -> bucket=%s outcome=%s",
        call.Id,
        call.Type,
        call.Path,
        call.Duration,
        call.Date,
        bucket,
        outcome,
    )


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
        """Download the shared call list once and split/limit it per bucket.

        A single ``get_calls(calltype=ALL_CALL_TYPES, update=True, ...)``
        downloads the raw, combined call list from the FRITZ!Box exactly
        once per polling cycle; every call is then classified and sorted
        into one of our three buckets client-side via ``_classify_call``
        (unmapped raw types - the two transient "call in progress" ones -
        are skipped). The computed outcome is stashed as a dynamic
        ``outcome`` attribute directly on the ``Call`` instance so
        ``sensor.py`` can read it without recomputing the classification.
        """
        raw_calls = self._fritz_call.get_calls(
            calltype=ALL_CALL_TYPES,
            update=True,
            days=SHARED_CALL_LOG_FETCH_DAYS,
        )

        unsorted_by_type: dict[str, list[Call]] = {call_type: [] for call_type in CALL_TYPES}
        for call in raw_calls:
            bucket, outcome = _classify_call(call)
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _log_raw_call_for_diagnostics(call, bucket, outcome)
            if bucket is None:
                continue
            call.outcome = outcome
            unsorted_by_type[bucket].append(call)

        calls_by_type = {
            call_type: self._apply_limit(calls, call_type)
            for call_type, calls in unsorted_by_type.items()
        }
        return CallLogData(calls_by_type=calls_by_type)

    def get_call(self, call_type: str, call_id: str) -> Call | None:
        """Look up one currently-known call by its bucket + raw Id string.

        Used by http.py's FritzBoxCallMediaView to resolve a "Weiterver-
        arbeitung" download link back to the specific Call it came from.
        """
        if self.data is None:
            return None
        for call in self.data.calls(call_type):
            if str(call.id) == call_id:
                return call
        return None

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
