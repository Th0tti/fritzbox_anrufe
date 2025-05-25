"""Sensor to monitor incoming/outgoing phone calls on a Fritz!Box router."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from enum import StrEnum
import logging
import queue
from threading import Event as ThreadingEvent, Thread
from time import sleep
from typing import Any, cast

from fritzconnection.core.fritzmonitor import FritzMonitor

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from .base import FritzBoxPhonebook
from .const import DOMAIN, FritzState

SCAN_INTERVAL = timedelta(hours=3)

class CallState(StrEnum):
    """Fritz sensor call states."""

    RINGING = "ringing"
    DIALING = "dialing"
    TALKING = "talking"
    IDLE = "idle"

async def async_setup_entry(
    hass,
    config_entry,
    async_add_entities,
) -> None:
    """Set up the fritzbox_anrufe sensor from config_entry."""
    fritzbox_phonebook = hass.data[DOMAIN][config_entry.entry_id]
    phonebook_id = config_entry.data[CONF_PHONEBOOK]
    prefixes = config_entry.options.get(CONF_PREFIXES)
    serial_number = config_entry.data[SERIAL_NUMBER]
    host = config_entry.data[CONF_HOST]
    port = config_entry.data[CONF_PORT]

    unique_id = f"{serial_number}-{phonebook_id}"
    sensor = FritzBoxCallSensor(
        phonebook_name=config_entry.title,
        unique_id=unique_id,
        phonebook_id=phonebook_id,
        prefixes=prefixes,
        fritzbox= fritzbox_phonebook,
    )
    async_add_entities([sensor], update_before_add=True)

class FritzBoxCallSensor(SensorEntity):
    """Sensor that reports call state and attributes."""

    _attr_device_class = SensorDeviceClass.PHONE
    _attr_name = "FRITZ!Box Anrufe"

    def __init__(self, phonebook_name, unique_id, phonebook_id, prefixes, fritzbox):
        self._attr_unique_id = unique_id
        self._sensor = fritzbox
        self._phonebook_id = phonebook_id
        self._prefixes = prefixes
        self._monitor_queue: queue.Queue[tuple[str, ...]] = queue.Queue()
        self._monitor_thread: Thread | None = None
        self._monitor_stop: ThreadingEvent | None = None

    def _start_monitor(self) -> None:
        """Start FritzMonitor thread."""
        self._monitor = FritzMonitor(
            address=self._sensor.host,
            port=self._sensor.port,
            user=self._sensor.username,
            password=self._sensor.password,
            call_trigger=self._monitor_queue.put,
        )
        self._monitor.connect()

    # … hier folgt die Logik für CALLBACKS, Trennen, Attributpflege, unverändert übernehmen …
