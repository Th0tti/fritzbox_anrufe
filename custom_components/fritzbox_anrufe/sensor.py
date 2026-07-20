"""Sensor to monitor incoming/outgoing phone calls on a Fritz!Box router."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from enum import StrEnum
import logging
import queue
from threading import Event as ThreadingEvent, Thread
from time import sleep
from typing import Any, cast, override

from fritzconnection.core.fritzmonitor import FritzMonitor
from fritzconnection.lib.fritzcall import OUT_CALL_TYPE, Call

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FritzBoxCallMonitorConfigEntry, FritzBoxRuntimeData
from .base import Contact, FritzBoxPhonebook
from .call_log import FritzCallLogCoordinator
from .const import (
    ATTR_PREFIXES,
    CALL_MEDIA_URL_BASE,
    CALL_OUTCOME_NOT_CONNECTED,
    CALL_TYPE_LIVE,
    CALL_TYPE_OUTGOING,
    CALL_TYPE_VOICEMAIL,
    CALL_TYPES,
    CONF_PHONEBOOK,
    CONF_PREFIXES,
    DOMAIN,
    MANUFACTURER,
    POST_CALL_REFRESH_DELAY_SECONDS,
    SERIAL_NUMBER,
    TAM_MEDIA_URL_BASE,
    FritzState,
)
from .tam import TamMessage
from .voicemail import FritzTamCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=3)


class CallState(StrEnum):
    """Fritz sensor call states."""

    RINGING = "ringing"
    DIALING = "dialing"
    TALKING = "talking"
    IDLE = "idle"


def _build_device_info(fritzbox_phonebook: FritzBoxPhonebook, unique_id: str) -> DeviceInfo:
    """Build the shared device info for all sensors of one FRITZ!Box account."""
    return DeviceInfo(
        configuration_url=fritzbox_phonebook.fph.fc.address,
        identifiers={(DOMAIN, unique_id)},
        manufacturer=MANUFACTURER,
        model=fritzbox_phonebook.fph.modelname,
        name=fritzbox_phonebook.fph.modelname,
        sw_version=fritzbox_phonebook.fph.fc.system_version,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: FritzBoxCallMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the fritzbox_anrufe sensors from config_entry."""
    runtime_data: FritzBoxRuntimeData = config_entry.runtime_data
    fritzbox_phonebook = runtime_data.phonebook
    call_log_coordinator = runtime_data.call_log_coordinator
    tam_coordinator = runtime_data.tam_coordinator

    phonebook_id: int = config_entry.data[CONF_PHONEBOOK]
    prefixes: list[str] | None = config_entry.options.get(CONF_PREFIXES)
    serial_number: str = config_entry.data[SERIAL_NUMBER]
    host: str = config_entry.data[CONF_HOST]
    port: int = config_entry.data[CONF_PORT]

    unique_id = f"{serial_number}-{phonebook_id}"
    device_info = _build_device_info(fritzbox_phonebook, unique_id)

    live_sensor = FritzBoxCallSensor(
        phonebook_name=config_entry.title,
        unique_id=unique_id,
        fritzbox_phonebook=fritzbox_phonebook,
        prefixes=prefixes,
        host=host,
        port=port,
        device_info=device_info,
        call_log_coordinator=call_log_coordinator,
        tam_coordinator=tam_coordinator,
    )

    call_list_sensors = [
        FritzBoxCallListSensor(
            coordinator=call_log_coordinator,
            call_type=call_type,
            unique_id=f"{unique_id}-{call_type}",
            phonebook_name=config_entry.title,
            fritzbox_phonebook=fritzbox_phonebook,
            device_info=device_info,
            config_entry_id=config_entry.entry_id,
        )
        for call_type in CALL_TYPES
    ]

    entities: list[SensorEntity] = [live_sensor, *call_list_sensors]

    # Anrufbeantworter-Sensor (EXPERIMENTELL, siehe tam.py). Nur hinzufügen,
    # wenn der Coordinator tatsächlich erstellt werden konnte - er wird nie
    # None sein (siehe __init__.py), das defensive `is not None` schützt
    # nur gegen künftige Änderungen an dieser Voraussetzung.
    if tam_coordinator is not None:
        entities.append(
            FritzBoxVoicemailSensor(
                coordinator=tam_coordinator,
                unique_id=f"{unique_id}-{CALL_TYPE_VOICEMAIL}",
                phonebook_name=config_entry.title,
                fritzbox_phonebook=fritzbox_phonebook,
                device_info=device_info,
                config_entry_id=config_entry.entry_id,
            )
        )

    async_add_entities(entities)


class FritzBoxCallSensor(SensorEntity):
    """Implementation of a Fritz!Box call monitor."""

    _attr_has_entity_name = True
    _attr_translation_key = f"{DOMAIN}_{CALL_TYPE_LIVE}"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(CallState)

    def __init__(
        self,
        phonebook_name: str,
        unique_id: str,
        fritzbox_phonebook: FritzBoxPhonebook,
        prefixes: list[str] | None,
        host: str,
        port: int,
        device_info: DeviceInfo,
        call_log_coordinator: FritzCallLogCoordinator,
        tam_coordinator: FritzTamCoordinator | None,
    ) -> None:
        """Initialize the sensor."""
        self._fritzbox_phonebook = fritzbox_phonebook
        self._prefixes = prefixes
        self._host = host
        self._port = port
        self._monitor: FritzBoxCallMonitor | None = None
        self._attributes: dict[str, str | list[str] | bool] = {}
        # Used by _schedule_post_call_refresh() (since v1.0.3, see its
        # docstring) to trigger an extra call-list/AB refresh shortly after
        # a call ends, on top of both coordinators' regular 5-minute polling.
        self._call_log_coordinator = call_log_coordinator
        self._tam_coordinator = tam_coordinator

        self._attr_translation_placeholders = {"phonebook_name": phonebook_name}
        self._attr_unique_id = unique_id
        self._attr_native_value = CallState.IDLE
        self._attr_device_info = device_info

    @override
    async def async_added_to_hass(self) -> None:
        """Connect to FRITZ!Box to monitor its call state."""
        await super().async_added_to_hass()
        await self.hass.async_add_executor_job(self._start_call_monitor)
        self.async_on_remove(
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, self._stop_call_monitor
            )
        )

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Disconnect from FRITZ!Box by stopping monitor."""
        await super().async_will_remove_from_hass()
        await self.hass.async_add_executor_job(self._stop_call_monitor)

    def _start_call_monitor(self) -> None:
        """Check connection and start callmonitor thread."""
        _LOGGER.debug("Starting monitor for: %s", self.entity_id)
        self._monitor = FritzBoxCallMonitor(
            host=self._host,
            port=self._port,
            sensor=self,
        )
        self._monitor.connect()

    def _stop_call_monitor(self, event: Event | None = None) -> None:
        """Stop callmonitor thread."""
        if (
            self._monitor
            and self._monitor.stopped
            and not self._monitor.stopped.is_set()
            and self._monitor.connection
            and self._monitor.connection.is_alive
        ):
            self._monitor.stopped.set()
            self._monitor.connection.stop()
            _LOGGER.debug("Stopped monitor for: %s", self.entity_id)

    def set_state(self, state: CallState) -> None:
        """Set the state; also triggers a post-call refresh (see below)."""
        previous_state = self._attr_native_value
        self._attr_native_value = state
        # Any transition back to idle after a non-idle state means a call
        # just ended - whether it was actually answered (RINGING/DIALING ->
        # TALKING -> IDLE) or missed (RINGING -> IDLE with no TALKING in
        # between). Either way, the call-list/AB coordinators' data is now
        # stale until their next regular 5-minute poll - refresh them early
        # instead of waiting.
        if state == CallState.IDLE and previous_state != CallState.IDLE:
            self._schedule_post_call_refresh()

    def _schedule_post_call_refresh(self) -> None:
        """Schedule an extra coordinator refresh shortly after a call ends.

        This runs on FritzBoxCallMonitor's background thread (see
        _process_events/_parse below), NOT the Home Assistant event loop -
        same constraint as schedule_update_ha_state(), which uses the same
        call_soon_threadsafe hand-off. A short delay
        (POST_CALL_REFRESH_DELAY_SECONDS, see const.py) gives the FRITZ!Box
        a moment to finalize the new call-list entry and, if applicable,
        process a freshly recorded answering-machine message before this
        integration asks for it - polling immediately on disconnect risked
        a race where the entry (or the TAM message used to match it, see
        call_log.py:_find_matching_tam_message) wasn't there yet.
        """
        if self.hass is None:
            return
        self.hass.loop.call_soon_threadsafe(self._async_schedule_post_call_refresh)

    @callback
    def _async_schedule_post_call_refresh(self) -> None:
        """Event-loop-side half of _schedule_post_call_refresh()."""
        async_call_later(
            self.hass, POST_CALL_REFRESH_DELAY_SECONDS, self._async_refresh_after_call
        )

    async def _async_refresh_after_call(self, _now: Any = None) -> None:
        """Refresh the call-list coordinator, and the AB one if present."""
        await self._call_log_coordinator.async_request_refresh()
        if self._tam_coordinator is not None:
            await self._tam_coordinator.async_request_refresh()

    def record_failed_outgoing_call(self, pending: Mapping[str, str]) -> None:
        """Build and hand off a synthetic Call for a failed outgoing dial.

        Called by FritzBoxCallMonitor._parse() (same background thread as
        set_state()/_schedule_post_call_refresh() above) when a DISCONNECT
        arrives for a ConnectionID that reached CALL (dialing) but never
        CONNECT (talking) - i.e. an outgoing call that was busy, unanswered,
        or cancelled before pickup. Per Thorsten (confirmed on his own
        FRITZ!Box): such attempts never appear in the FRITZ!Box's own
        TR-064 call list at all, even with a zero duration - an outgoing
        call is only logged there once a connection was actually
        established. add_synthetic_outgoing_call() itself is a plain,
        lock-protected append, safe to call directly from this thread - see
        call_log.py for how it's merged into the "ausgehend" bucket on the
        next _fetch_calls() (including the already-scheduled post-call
        refresh triggered by set_state() for this very same DISCONNECT).
        """
        call = Call()
        call.Id = f"live-{pending['raw_date']}-{pending['number']}"
        call.Type = str(OUT_CALL_TYPE)
        call.Date = pending["call_date"]
        call.Duration = "0:00"
        call.Caller = pending["own_number"]
        call.Called = pending["number"]
        call.Device = pending["device"]
        call.Path = None
        call.outcome = CALL_OUTCOME_NOT_CONNECTED
        call.tam_message = None
        self._call_log_coordinator.add_synthetic_outgoing_call(call)

    def set_attributes(self, attributes: Mapping[str, str | bool]) -> None:
        """Set the state attributes."""
        self._attributes = {**attributes}

    @property
    @override
    def extra_state_attributes(self) -> dict[str, str | list[str] | bool]:
        """Return the state attributes."""
        if self._prefixes:
            self._attributes[ATTR_PREFIXES] = self._prefixes
        return self._attributes

    def number_to_contact(self, number: str) -> Contact:
        """Return a contact for a given phone number."""
        return self._fritzbox_phonebook.get_contact(number)

    def update(self) -> None:
        """Update the phonebook if it is defined."""
        self._fritzbox_phonebook.update_phonebook()


class FritzBoxCallListSensor(CoordinatorEntity[FritzCallLogCoordinator], SensorEntity):
    """Historical call-list sensor: fritzbox_anrufe_eingehend/ausgehend/verpasst.

    Unlike :class:`FritzBoxCallSensor` (live status via the call monitor),
    this sensor is fed by :class:`FritzCallLogCoordinator`, which polls the
    FRITZ!Box call list via TR-064. Its state is the number of calls
    currently held, the full list is exposed as the ``calls`` attribute so
    it can be rendered as a table on a dashboard.
    """

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "Anrufe"

    def __init__(
        self,
        coordinator: FritzCallLogCoordinator,
        call_type: str,
        unique_id: str,
        phonebook_name: str,
        fritzbox_phonebook: FritzBoxPhonebook,
        device_info: DeviceInfo,
        config_entry_id: str,
    ) -> None:
        """Initialize the call-list sensor."""
        super().__init__(coordinator)
        self._call_type = call_type
        self._fritzbox_phonebook = fritzbox_phonebook
        self._config_entry_id = config_entry_id

        # translation_key selects the matching icon (icons.json) and the
        # localized name (strings.json, entity.sensor.fritzbox_anrufe_<type>).
        # NOTE: the resulting entity_id is auto-derived from the device name
        # plus this translated entity name (e.g.
        # "sensor.fritz_box_7590_eingehende_anrufe"), it is *not* forced to
        # literally read "fritzbox_anrufe_eingehend" - Home Assistant has no
        # supported hook for a config-entry/unique_id-based entity to dictate
        # its own object_id. If you want that exact entity_id, rename the
        # entity once in Settings -> Devices & Services -> Entities (gear
        # icon -> "Entity ID"); the rename persists in the entity registry.
        self._attr_translation_key = f"{DOMAIN}_{call_type}"
        self._attr_translation_placeholders = {"phonebook_name": phonebook_name}
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info

    @property
    def _calls(self) -> list[Call]:
        """Return the raw Call objects for this sensor's call type."""
        if self.coordinator.data is None:
            return []
        return self.coordinator.data.calls(self._call_type)

    @property
    @override
    def native_value(self) -> int:
        """Return the number of calls currently held by this sensor."""
        return len(self._calls)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, list[dict[str, Any]]]:
        """Return the calls as a list of dicts, e.g. for a dashboard table."""
        return {"calls": [self._call_to_dict(call) for call in self._calls]}

    def _call_to_dict(self, call: Call) -> dict[str, Any]:
        """Convert one Call instance into a flat, table-friendly dict."""
        is_outgoing = self._call_type == CALL_TYPE_OUTGOING
        external_number = call.Called if is_outgoing else call.Caller
        own_number = call.Caller if is_outgoing else call.Called

        contact = None
        if external_number:
            contact = self._fritzbox_phonebook.get_contact(external_number)

        duration = call.duration
        # "outcome" and "tam_message" are set by
        # FritzCallLogCoordinator._fetch_calls() (see
        # call_log.py:_classify_call/_find_matching_tam_message) as dynamic
        # attributes directly on the Call instance. "outcome" is used by the
        # dashboard card's optional "Weiterverarbeitung" row (since v1.0.3)
        # to pick an icon/action. For media_url, a confidently matched
        # tam_message is preferred - it points at the TAM sensor's own,
        # already real-hardware-confirmed media proxy (see http.py:
        # FritzBoxTamMediaView) instead of the newer, unconfirmed call-list
        # one; call.Path alone is only used as a fallback when no match was
        # found (e.g. the TAM coordinator hasn't polled yet).
        outcome = getattr(call, "outcome", None)
        tam_message = getattr(call, "tam_message", None)
        media_url = None
        if tam_message is not None and tam_message.Path:
            media_url = f"{TAM_MEDIA_URL_BASE}/{self._config_entry_id}/{tam_message.Index}"
        elif call.Path:
            media_url = f"{CALL_MEDIA_URL_BASE}/{self._config_entry_id}/{self._call_type}/{call.id}"
        return {
            "type": self._call_type,
            "date": call.date.isoformat() if isinstance(call.date, datetime) else None,
            "name": call.Name or (contact.name if contact else None),
            "number": external_number or None,
            "own_number": own_number or None,
            "device": call.Device or None,
            "duration": str(duration) if isinstance(duration, timedelta) else None,
            "vip": contact.vip if contact else False,
            "outcome": outcome,
            "media_url": media_url,
        }


class FritzBoxVoicemailSensor(CoordinatorEntity[FritzTamCoordinator], SensorEntity):
    """Answering-machine sensor: fritzbox_anrufe_anrufbeantworter.

    EXPERIMENTAL - see the module docstring in ``tam.py``. Fed by
    :class:`FritzTamCoordinator`, which polls the FRITZ!Box answering
    machine (TAM) message list via TR-064. Its state is the number of
    messages currently held, the full list (incl. a playable
    ``media_url`` per message, served by the authenticated proxy in
    ``http.py``) is exposed as the ``messages`` attribute.
    """

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "Nachrichten"
    _attr_icon = "mdi:voicemail"

    def __init__(
        self,
        coordinator: FritzTamCoordinator,
        unique_id: str,
        phonebook_name: str,
        fritzbox_phonebook: FritzBoxPhonebook,
        device_info: DeviceInfo,
        config_entry_id: str,
    ) -> None:
        """Initialize the answering-machine sensor."""
        super().__init__(coordinator)
        self._fritzbox_phonebook = fritzbox_phonebook
        self._config_entry_id = config_entry_id

        self._attr_translation_key = f"{DOMAIN}_{CALL_TYPE_VOICEMAIL}"
        self._attr_translation_placeholders = {"phonebook_name": phonebook_name}
        self._attr_unique_id = unique_id
        self._attr_device_info = device_info

    @property
    def _messages(self) -> list[TamMessage]:
        """Return the raw TamMessage objects currently held."""
        return self.coordinator.data or []

    @property
    @override
    def native_value(self) -> int:
        """Return the number of answering-machine messages currently held."""
        return len(self._messages)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, list[dict[str, Any]]]:
        """Return the messages as a list of dicts, e.g. for a dashboard."""
        return {"messages": [self._message_to_dict(message) for message in self._messages]}

    def _message_to_dict(self, message: TamMessage) -> dict[str, Any]:
        """Convert one TamMessage instance into a flat, table-friendly dict."""
        contact = None
        if message.Number:
            contact = self._fritzbox_phonebook.get_contact(message.Number)

        duration = message.duration
        media_url = (
            f"{TAM_MEDIA_URL_BASE}/{self._config_entry_id}/{message.Index}"
            if message.Path
            else None
        )
        return {
            "name": message.Name or (contact.name if contact else None),
            "number": message.Number or None,
            "date": message.date.isoformat() if isinstance(message.date, datetime) else None,
            "duration": str(duration) if isinstance(duration, timedelta) else None,
            "new": bool(message.new),
            "vip": contact.vip if contact else False,
            "media_url": media_url,
        }


class FritzBoxCallMonitor:
    """Event listener to monitor calls on the Fritz!Box."""

    def __init__(self, host: str, port: int, sensor: FritzBoxCallSensor) -> None:
        """Initialize Fritz!Box monitor instance."""
        self.host = host
        self.port = port
        self.connection: FritzMonitor | None = None
        self.stopped = ThreadingEvent()
        self._sensor = sensor
        # Dial attempts (CALL events) currently "in flight", keyed by the
        # callmonitor's own ConnectionID (line[2], stable across CALL ->
        # CONNECT/DISCONNECT for the same call, and distinct per line so
        # overlapping calls don't get mixed up) - cleared on CONNECT (the
        # call succeeded, the FRITZ!Box's own call list will log it
        # normally) or consumed on DISCONNECT with no prior CONNECT (see
        # _parse below and FritzBoxCallSensor.record_failed_outgoing_call).
        self._pending_outgoing: dict[str, dict[str, str]] = {}

    def connect(self) -> None:
        """Connect to the Fritz!Box."""
        _LOGGER.debug("Setting up socket connection")
        try:
            self.connection = FritzMonitor(address=self.host, port=self.port)
            kwargs: dict[str, Any] = {
                "event_queue": self.connection.start(
                    reconnect_tries=50, reconnect_delay=120
                )
            }
            Thread(target=self._process_events, kwargs=kwargs).start()
        except OSError as err:
            self.connection = None
            _LOGGER.error(
                "Cannot connect to %s on port %s: %s", self.host, self.port, err
            )

    def _process_events(self, event_queue: queue.Queue[str]) -> None:
        """Listen to incoming or outgoing calls."""
        _LOGGER.debug("Connection established, waiting for events")
        while not self.stopped.is_set():
            try:
                event = event_queue.get(timeout=10)
            except queue.Empty:
                if (
                    not cast(FritzMonitor, self.connection).is_alive
                    and not self.stopped.is_set()
                ):
                    _LOGGER.error("Connection has abruptly ended")
                _LOGGER.debug("Empty event queue")
                continue
            else:
                _LOGGER.debug("Received event: %s", event)
                self._parse(event)
                sleep(1)

    def _parse(self, event: str) -> None:
        """Parse the call information and set the sensor states."""
        line = event.split(";")
        df_in = "%d.%m.%y %H:%M:%S"
        df_out = "%Y-%m-%dT%H:%M:%S"
        call_date = datetime.strptime(line[0], df_in)
        isotime = call_date.strftime(df_out)
        # Same event timestamp, but reformatted to the minute-precision
        # "%d.%m.%y %H:%M" the FRITZ!Box's own TR-064 call list uses for
        # its Date field (see call_log.py:_find_matching_tam_message for
        # the other place this exact format matters) - used only if this
        # turns out to be a failed outgoing dial, see FritzState.CALL below.
        call_date_str = call_date.strftime("%d.%m.%y %H:%M")
        connection_id = line[2]
        att: dict[str, str | bool]
        if line[1] == FritzState.RING:
            self._sensor.set_state(CallState.RINGING)
            contact = self._sensor.number_to_contact(line[3])
            att = {
                "type": "incoming",
                "from": line[3],
                "to": line[4],
                "device": line[5],
                "initiated": isotime,
                "from_name": contact.name,
                "vip": contact.vip,
            }
            self._sensor.set_attributes(att)
        elif line[1] == FritzState.CALL:
            self._sensor.set_state(CallState.DIALING)
            # Remember this dial attempt until we know whether it succeeds
            # (CONNECT) or not (DISCONNECT with no CONNECT in between) -
            # see those branches below.
            self._pending_outgoing[connection_id] = {
                "own_number": line[4],
                "number": line[5],
                "device": line[6],
                "raw_date": line[0],
                "call_date": call_date_str,
            }
            contact = self._sensor.number_to_contact(line[5])
            att = {
                "type": "outgoing",
                "from": line[4],
                "to": line[5],
                "device": line[6],
                "initiated": isotime,
                "to_name": contact.name,
                "vip": contact.vip,
            }
            self._sensor.set_attributes(att)
        elif line[1] == FritzState.CONNECT:
            self._sensor.set_state(CallState.TALKING)
            # This ConnectionID connected - a dial attempt that reaches
            # here succeeded, the FRITZ!Box's own call list will log it
            # normally, so nothing further to track for it.
            self._pending_outgoing.pop(connection_id, None)
            contact = self._sensor.number_to_contact(line[4])
            att = {
                "with": line[4],
                "device": line[3],
                "accepted": isotime,
                "with_name": contact.name,
                "vip": contact.vip,
            }
            self._sensor.set_attributes(att)
        elif line[1] == FritzState.DISCONNECT:
            self._sensor.set_state(CallState.IDLE)
            pending = self._pending_outgoing.pop(connection_id, None)
            if pending is not None:
                # Reached CALL but never CONNECT for this ConnectionID - a
                # failed outgoing dial attempt (busy, unanswered, or
                # cancelled before pickup). See
                # FritzBoxCallSensor.record_failed_outgoing_call for why
                # this needs to be synthesized here at all.
                self._sensor.record_failed_outgoing_call(pending)
            att = {"duration": line[3], "closed": isotime}
            self._sensor.set_attributes(att)
        self._sensor.schedule_update_ha_state()
