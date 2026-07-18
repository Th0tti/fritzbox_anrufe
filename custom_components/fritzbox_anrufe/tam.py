"""Wrapper around the FRITZ!Box answering machine (TAM) TR-064 API.

EXPERIMENTAL / UNVERIFIED AGAINST REAL HARDWARE
-------------------------------------------------
This module was written by researching AVM's TR-064 service description
for the ``X_AVM-DE_TAM1`` service and the ``GetMessageList`` action, and by
mirroring the *exact same* download pattern that :mod:`fritzconnection`
itself already uses for the (confirmed working, real-hardware-tested) call
list in :mod:`fritzconnection.lib.fritzcall`:

1. Call a SOAP action that returns a session-authenticated URL to an XML
   document (``GetCallList`` -> ``NewCallListURL`` for calls; here
   ``GetMessageList`` -> presumably ``NewURL`` for TAM messages).
2. Download that URL using the already-authenticated
   :class:`~fritzconnection.core.fritzconnection.FritzConnection` session
   (``fc.session``, a :class:`requests.Session` with FRITZ!Box digest auth
   already attached) via :func:`fritzconnection.core.utils.get_xml_root`.
3. Parse the resulting XML into plain Python objects using
   :mod:`fritzconnection`'s own generic node processor
   (:mod:`fritzconnection.core.processor`), exactly like ``CallCollection``
   does for calls.

Unlike the call list, this could **not** be verified against a real
FRITZ!Box while building this integration. In particular, AVM's own
documentation and third-party references are inconsistent about the exact
name of ``GetMessageList``'s output parameter - some call it ``NewURL``,
others ``NewMessageListURL``. :meth:`FritzTam._message_list_url` therefore
checks both names defensively. If your FRITZ!Box uses a different name (or
a different service/action entirely), the voicemail sensor will simply
report 0 messages and log a warning rather than breaking the rest of the
integration - please open a GitHub issue with the log output so this can
be fixed for real hardware.
"""

from __future__ import annotations

import datetime
import logging

from fritzconnection.core.fritzconnection import FritzConnection
from fritzconnection.core.processor import (
    InstanceAttributeFactory,
    Storage,
    process_node,
    processor,
)
from fritzconnection.core.utils import get_xml_root

_LOGGER = logging.getLogger(__name__)

SERVICE = "X_AVM-DE_TAM1"
ACTION_GET_MESSAGE_LIST = "GetMessageList"

# Some FRITZ!OS versions expose more than one answering machine ("TAM
# index" 0, 1, ...). We only support the first/default one for now.
DEFAULT_TAM_INDEX = "0"

# See the module docstring: the exact output parameter name of
# GetMessageList could not be confirmed against real hardware, so both
# known candidates are checked, in order of how likely they are correct
# (mirroring GetCallList's "NewCallListURL" naming convention).
_URL_RESULT_KEYS = ("NewURL", "NewMessageListURL")


def _datetime_converter(date_string: str | None) -> datetime.datetime | str | None:
    if not date_string:
        return date_string
    return datetime.datetime.strptime(date_string, "%d.%m.%y %H:%M")


def _timedelta_converter(duration_string: str | None) -> datetime.timedelta | str | None:
    if not duration_string:
        return duration_string
    hours, minutes = (int(part) for part in duration_string.split(":", 1))
    return datetime.timedelta(hours=hours, minutes=minutes)


def _bool_converter(value: str | None) -> bool:
    return str(value) == "1"


class _AttributeConverter:
    """Data descriptor returning a converted attribute value (read-only)."""

    def __init__(self, attribute_name: str, converter=str) -> None:
        self.attribute_name = attribute_name
        self.converter = converter

    def __set__(self, obj, value):
        return NotImplemented

    def __get__(self, obj, objtype):
        attr = getattr(obj, self.attribute_name)
        try:
            return self.converter(attr)
        except (TypeError, ValueError):
            return attr


@processor
class TamMessage:
    """One answering-machine message.

    Instance attributes are named exactly like the XML nodes AVM is
    expected to use (mirroring how :class:`fritzconnection.lib.fritzcall.Call`
    is modeled): ``Index``, ``Number``, ``Date``, ``Duration``, ``Name``,
    ``Path`` (relative/absolute URL to the audio recording, FRITZ!Box-
    session-authenticated), ``New`` ("1"/"0") and ``Count``. Lowercase
    convenience properties expose converted values: ``date`` (datetime),
    ``duration`` (timedelta), ``new`` (bool).
    """

    date = _AttributeConverter("Date", _datetime_converter)
    duration = _AttributeConverter("Duration", _timedelta_converter)
    new = _AttributeConverter("New", _bool_converter)

    def __init__(self) -> None:
        self.Index: str | None = None
        self.Number: str | None = None
        self.Date: str | None = None
        self.Duration: str | None = None
        self.Name: str | None = None
        self.Path: str | None = None
        self.New: str | None = None
        self.Count: str | None = None


class TamMessageCollection(Storage):
    """Container for a sequence of :class:`TamMessage` instances."""

    Message = InstanceAttributeFactory(TamMessage)

    def __init__(self, root) -> None:
        self.messages: list[TamMessage] = []
        super().__init__(self.messages)
        process_node(self, root)

    def __iter__(self):
        return iter(self.messages)


class FritzTam:
    """Access the FRITZ!Box answering-machine message list via TR-064."""

    def __init__(self, fc: FritzConnection, index: str = DEFAULT_TAM_INDEX) -> None:
        """Initialize with an already-authenticated FritzConnection.

        Reuses the same connection/session the rest of the integration
        already opened (see ``__init__.py``), so no extra FRITZ!Box login
        is required for the answering machine.
        """
        self.fc = fc
        self.index = index

    def _message_list_url(self) -> str | None:
        """Call GetMessageList and return the message-list XML URL, if any."""
        result = self.fc.call_action(
            SERVICE, ACTION_GET_MESSAGE_LIST, arguments={"NewIndex": self.index}
        )
        for key in _URL_RESULT_KEYS:
            url = result.get(key)
            if url:
                return str(url)
        _LOGGER.warning(
            "Anrufbeantworter: GetMessageList lieferte keinen der erwarteten"
            " URL-Schlüssel (%s) zurück - Antwort war: %s. Bitte als GitHub"
            " Issue melden, damit die Anrufbeantworter-Anbindung an die"
            " tatsächliche FRITZ!OS-Version angepasst werden kann.",
            _URL_RESULT_KEYS,
            sorted(result.keys()),
        )
        return None

    def get_messages(self) -> list[TamMessage]:
        """Return all answering-machine messages, as delivered by the box."""
        url = self._message_list_url()
        if not url:
            return []
        root = get_xml_root(url, session=self.fc.session)
        return list(TamMessageCollection(root))
