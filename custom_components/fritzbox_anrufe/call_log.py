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

Failed outgoing calls are invisible to TR-064 (since v1.0.3)
--------------------------------------------------------------
Per Thorsten, confirmed against his own FRITZ!Box: an outgoing call only
ever appears in the TR-064 call list once a connection was actually
established - a busy signal, an unanswered dial, or a call cancelled before
pickup is not logged there at all, not even with a zero duration (the
"only duration is derivable, no distinct busy signal" limitation noted
elsewhere in this codebase turned out to understate the gap - such calls
are entirely absent, not just ambiguous). The only place such an attempt is
observable at all is the live call monitor (RING/CALL/CONNECT/DISCONNECT
events, TCP port 1012) - see ``sensor.py``'s ``FritzBoxCallMonitor``, which
detects a CALL (dialing) followed by a DISCONNECT with no intervening
CONNECT and hands a synthetic :class:`~fritzconnection.lib.fritzcall.Call`
to :meth:`FritzCallLogCoordinator.add_synthetic_outgoing_call`. These are
buffered in-memory (``_synthetic_outgoing_calls``, thread-safe via
``_synthetic_outgoing_lock`` since the callmonitor hands them off from its
own background thread) and merged into the "ausgehend" bucket on every
``_fetch_calls()``, de-duplicated against the just-downloaded TR-064 data
by (minute, called number) in case a future FRITZ!OS version ever does log
them after all. Being in-memory only, they do not survive a Home Assistant
restart - only attempts observed while this integration is running show up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from threading import Lock

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
    CALL_OUTCOME_NO_VOICEMAIL,
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
    DEVICE_ANSWERING_MACHINE,
    SHARED_CALL_LOG_FETCH_DAYS,
    conf_call_log_count,
    conf_call_log_days,
    conf_call_log_limit_type,
)
from .tam import TamMessage
from .voicemail import FritzTamCoordinator

_LOGGER = logging.getLogger(__name__)

CALL_LOG_UPDATE_INTERVAL = timedelta(minutes=5)


def _find_matching_tam_message(call: Call, tam_messages: list[TamMessage]) -> TamMessage | None:
    """Find the answering-machine message (if any) this call produced.

    Both ``Call.date`` and ``TamMessage.date`` are minute-precision only -
    confirmed by inspecting the exact datetime formats each side parses
    (``fritzconnection``'s own ``datetime_converter`` for ``Call``, this
    integration's ``_datetime_converter`` in ``tam.py`` for ``TamMessage``:
    both use ``"%d.%m.%y %H:%M"``, no seconds) - so an exact match on that
    minute is a meaningful, ground-truth signal that a given call is the one
    that produced a given recording, rather than trusting the call list's
    own ``Path`` field in isolation (which is not always populated for such
    calls). The caller's number is compared too whenever both sides have
    one, to disambiguate the rare case of two calls landing in the same
    minute. Per Thorsten's suggestion (based on his own FRITZ!Box), this is
    what makes CALL_OUTCOME_VOICEMAIL vs. CALL_OUTCOME_UNREACHED trustworthy
    in practice.
    """
    if not isinstance(call.date, datetime):
        return None
    caller_number = call.Caller or None
    for message in tam_messages:
        if not isinstance(message.date, datetime) or message.date != call.date:
            continue
        if caller_number and message.Number and message.Number != caller_number:
            continue
        return message
    return None


def _classify_call(call: Call, matched_message: TamMessage | None) -> tuple[str | None, str | None]:
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
      call that went to the answering machine (with or without a recorded
      message) - AVM groups both under its own "incoming calls" filter.
      Since v1.0.3, this integration tells them apart primarily via
      ``call.Device`` - confirmed by Thorsten against his own hardware that
      a call routed to the built-in answering machine reports
      ``Device == DEVICE_ANSWERING_MACHINE`` regardless of whether a
      message was actually left. (An earlier v1.0.3 dev build used
      ``Path`` presence alone for this, which missed the case of a call
      routed to the AB with nothing recorded - such a call showed as
      CALL_TYPE_INCOMING/CALL_OUTCOME_ANSWERED, as if a person had
      answered.) ``has_recording`` (see below) is kept as an additional,
      independent trigger so a call still reclassifies as "verpasst" even
      if ``Device`` is ever empty/unexpected but a matching recording
      exists. "eingehend" therefore only ever contains genuinely
      person-answered calls.
    - Within CALL_TYPE_MISSED, whether a message was actually recorded is
      decided by ``matched_message`` (see ``_find_matching_tam_message``) -
      a date/time (and, where available, phone-number) match against the
      real answering-machine message list, a materially stronger signal
      than the call list's own ``Path`` field alone. ``call.Path`` is kept
      as an additional fallback trigger (e.g. if the TAM coordinator
      hasn't polled yet). Lacking a matched message, the outcome depends on
      whether the call ever reached the answering machine at all
      (``to_answering_machine``, same signal as above): CALL_OUTCOME_NO_VOICEMAIL
      if it did (per Thorsten: the previous single "Nicht erreicht" label
      was misleading here - the call *did* reach the answering machine, it
      just has no recorded message), CALL_OUTCOME_UNREACHED if it never got
      that far (blocked/rejected, or simply unanswered with no answering
      machine involved). The FRITZ!Box call list still does not expose a
      *further* distinction within CALL_OUTCOME_NO_VOICEMAIL between
      "caller hung up before the answering machine picked up" and "reached
      the answering machine's greeting but left no message". See the
      module-level ``_log_raw_call_for_diagnostics`` debug logging below,
      added to gather real examples of both cases before attempting a
      finer split.
    - For OUT_CALL_TYPE (3), only connection duration is evaluated: the
      FRITZ!Box call list does not expose a dedicated "busy" signal
      distinguishable from a plain unanswered outgoing call - both show as
      zero duration. See README, Fehlerbehebung.
    """
    to_answering_machine = (call.Device or "").strip() == DEVICE_ANSWERING_MACHINE
    has_recording = matched_message is not None or bool(call.Path)

    if call.type == RECEIVED_CALL_TYPE and not to_answering_machine and not has_recording:
        return CALL_TYPE_INCOMING, CALL_OUTCOME_ANSWERED

    if call.type in (RECEIVED_CALL_TYPE, MISSED_CALL_TYPE, REJECTED_CALL_TYPE):
        if has_recording:
            return CALL_TYPE_MISSED, CALL_OUTCOME_VOICEMAIL
        if to_answering_machine:
            return CALL_TYPE_MISSED, CALL_OUTCOME_NO_VOICEMAIL
        return CALL_TYPE_MISSED, CALL_OUTCOME_UNREACHED

    if call.type == OUT_CALL_TYPE:
        outcome = CALL_OUTCOME_CONNECTED if call.duration else CALL_OUTCOME_NOT_CONNECTED
        return CALL_TYPE_OUTGOING, outcome

    # ACTIVE_RECEIVED_CALL_TYPE (9) / ACTIVE_OUT_CALL_TYPE (11) - ignored.
    return None, None


def _log_raw_call_for_diagnostics(
    call: Call,
    bucket: str | None,
    outcome: str | None,
    matched_message: TamMessage | None,
) -> None:
    """Temporary DEBUG log of one call's raw fields alongside our classification.

    Added in v1.0.3 specifically to collect real-world examples for the
    still-unconfirmed distinction mentioned in ``_classify_call`` above
    (hung up before the answering machine vs. reached it without leaving a
    message). Enable debug logging for ``custom_components.fritzbox_anrufe``
    (Einstellungen -> Geräte & Dienste -> FRITZ!Box Anrufe -> Drei-Punkte-
    Menü -> "Debug-Protokollierung aktivieren", oder in configuration.yaml
    unter ``logger: logs:``) and reproduce a specific scenario to see the
    exact raw values here.
    """
    _LOGGER.debug(
        "Anrufliste: Id=%s Type=%s Device=%r Path=%r Duration=%r Date=%s"
        " -> bucket=%s outcome=%s matched_tam_message=%s",
        call.Id,
        call.Type,
        call.Device,
        call.Path,
        call.Duration,
        call.Date,
        bucket,
        outcome,
        matched_message.Index if matched_message is not None else None,
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
        tam_coordinator: FritzTamCoordinator | None = None,
    ) -> None:
        """Initialize the call log coordinator.

        ``tam_coordinator``, if given, supplies the answering-machine
        message list used by ``_find_matching_tam_message`` to classify
        calls (see ``_fetch_calls``/``_classify_call``) - pass ``None``
        only in tests; ``__init__.py`` always provides the real one.
        """
        super().__init__(
            hass,
            _LOGGER,
            name="fritzbox_anrufe call log",
            update_interval=CALL_LOG_UPDATE_INTERVAL,
        )
        self.config_entry = config_entry
        self._fritz_call = fritz_call
        self._tam_coordinator = tam_coordinator
        # Failed outgoing dial attempts observed via the live callmonitor -
        # see the module docstring and add_synthetic_outgoing_call() below.
        # Appended to from FritzBoxCallMonitor's background thread, read
        # from _fetch_calls() (an executor job, a different thread again) -
        # hence the lock, rather than relying on GIL-level atomicity.
        self._synthetic_outgoing_lock = Lock()
        self._synthetic_outgoing_calls: list[Call] = []

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
        once per polling cycle; every call is then matched against the
        answering-machine coordinator's currently-known messages (see
        ``_find_matching_tam_message`` - uses whatever ``self._tam_coordinator.data``
        already holds, does NOT trigger its own TAM refresh, to keep this a
        single-round-trip operation per polling cycle) and classified via
        ``_classify_call`` into one of our three buckets client-side
        (unmapped raw types - the two transient "call in progress" ones -
        are skipped). The computed outcome, and the matched message itself
        if any, are stashed as dynamic ``outcome``/``tam_message`` attributes
        directly on the ``Call`` instance so ``sensor.py`` can read them
        without recomputing the classification - ``tam_message`` in
        particular lets it point ``media_url`` at the already real-hardware-
        confirmed Anrufbeantworter media proxy instead of the newer,
        unconfirmed call-list one whenever a confident match exists (see
        ``sensor.py:_call_to_dict``).
        """
        raw_calls = self._fritz_call.get_calls(
            calltype=ALL_CALL_TYPES,
            update=True,
            days=SHARED_CALL_LOG_FETCH_DAYS,
        )
        tam_messages: list[TamMessage] = (
            (self._tam_coordinator.data if self._tam_coordinator is not None else None) or []
        )

        unsorted_by_type: dict[str, list[Call]] = {call_type: [] for call_type in CALL_TYPES}
        for call in raw_calls:
            matched_message = _find_matching_tam_message(call, tam_messages)
            bucket, outcome = _classify_call(call, matched_message)
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _log_raw_call_for_diagnostics(call, bucket, outcome, matched_message)
            if bucket is None:
                continue
            call.outcome = outcome
            call.tam_message = matched_message
            unsorted_by_type[bucket].append(call)

        # Failed outgoing dial attempts the FRITZ!Box's own TR-064 call
        # list never logs at all (see module docstring) - merged in here,
        # de-duplicated by (minute, called number) against what was just
        # downloaded in case a future FRITZ!OS version does log them after
        # all, then the combined "ausgehend" bucket is re-sorted by date
        # (newest first, matching the FRITZ!Box's own list order that
        # _apply_limit's "count" mode below relies on) since the synthetic
        # entries were not part of that original, already-sorted download.
        existing_outgoing_keys = {
            (call.date, call.Called)
            for call in unsorted_by_type[CALL_TYPE_OUTGOING]
            if isinstance(call.date, datetime)
        }
        for call in self._pop_synthetic_outgoing_calls():
            if (call.date, call.Called) in existing_outgoing_keys:
                continue
            unsorted_by_type[CALL_TYPE_OUTGOING].append(call)
        unsorted_by_type[CALL_TYPE_OUTGOING].sort(
            key=lambda call: call.date if isinstance(call.date, datetime) else datetime.min,
            reverse=True,
        )

        calls_by_type = {
            call_type: self._apply_limit(calls, call_type)
            for call_type, calls in unsorted_by_type.items()
        }
        return CallLogData(calls_by_type=calls_by_type)

    def add_synthetic_outgoing_call(self, call: Call) -> None:
        """Record a failed outgoing dial attempt observed via the live callmonitor.

        Thread-safe - called directly from FritzBoxCallMonitor's background
        thread (see sensor.py:FritzBoxCallSensor.record_failed_outgoing_call),
        NOT the Home Assistant event loop. Just buffers the call; it is
        merged into the "ausgehend" bucket on the next _fetch_calls() (see
        the module docstring for why this exists at all) - typically only
        a few seconds later, via the post-call refresh already scheduled by
        set_state() for this same call ending.
        """
        with self._synthetic_outgoing_lock:
            self._synthetic_outgoing_calls.append(call)

    def _pop_synthetic_outgoing_calls(self) -> list[Call]:
        """Thread-safely prune (to the shared fetch window) and snapshot the buffer."""
        cutoff = datetime.now() - timedelta(days=SHARED_CALL_LOG_FETCH_DAYS)
        with self._synthetic_outgoing_lock:
            self._synthetic_outgoing_calls = [
                call
                for call in self._synthetic_outgoing_calls
                if isinstance(call.date, datetime) and call.date >= cutoff
            ]
            return list(self._synthetic_outgoing_calls)

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
