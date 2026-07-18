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
from fritzconnection.lib.fritzcall import Call

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FritzBoxCallMonitorConfigEntry, FritzBoxRuntimeData
from .base import Contact, FritzBoxPhonebook
from .call_log import FritzCallLogCoordinator
from .const import (
    ATTR_PREFIXES,
    CALL_TYPE_LIVE,
    CALL_TYPE_OUTGOING,
    CALL_TYPE_VOICEMAIL,
    CALL_TYPES,
    CONF_PHONEBOOK,
    CONF_PREFIXES,
    DOMAIN,
    MANUFACTURER,
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
    )

    call_list_sensors = [
        FritzBoxCallListSensor(
            coordinator=call_log_coordinator,
            call_type=call_type,
            unique_id=f"{unique_id}-{call_type}",
            phonebook_name=config_entry.title,
            fritzbox_phonebook=fritzbox_phonebook,
            device_info=device_info,
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
    ) -> None:
        """Initialize the sensor."""
        self._fritzbox_phonebook = fritzbox_phonebook
        self._prefixes = prefixes
        self._host = host
        self._port = port
        self._monitor: FritzBoxCallMonitor | None = None
        self._attributes: dict[str, str | list[str] | bool] = {}

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
        """Set the state."""
        self._attr_native_value = state

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
    ) -> None:
        """Initialize the call-list sensor."""
        super().__init__(coordinator)
        self._call_type = call_type
        self._fritzbox_phonebook = fritzbox_phonebook

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
        return {
            "type": self._call_type,
            "date": call.date.isoformat() if isinstance(call.date, datetime) else None,
            "name": call.Name or (contact.name if contact else None),
            "number": external_number or None,
            "own_number": own_number or None,
            "device": call.Device or None,
            "duration": str(duration) if isinstance(duration, timedelta) else None,
            "vip": contact.vip if contact else False,
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
        isotime = datetime.strptime(line[0], df_in).strftime(df_out)
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
            att = {"duration": line[3], "closed": isotime}
            self._sensor.set_attributes(att)
        self._sensor.schedule_update_ha_state()
