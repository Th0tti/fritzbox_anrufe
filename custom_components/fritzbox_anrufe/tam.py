"""Wrapper around the FRITZ!Box answering machine (TAM) TR-064 API.

EXPERIMENTAL - message list confirmed working on real hardware; audio
download is a third attempt, see :func:`FritzTam.get_download_url` below
-------------------------------------------------------------------------
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

This part (message list) has been confirmed working against real hardware.
AVM's own documentation and third-party references are inconsistent about
the exact name of ``GetMessageList``'s output parameter - some call it
``NewURL``, others ``NewMessageListURL``. :meth:`FritzTam._message_list_url`
therefore checks both names defensively.

DOWNLOADING the actual recording is a separate problem and has gone through
several revisions:

1. GET ``download.lua?path=...`` with a classic-web-UI sid as a query
   parameter - 404 on real hardware.
2. POST to the same ``download.lua`` with the sid as form body data
   instead - identical 404 on real hardware. Since switching GET/POST and
   the sid mechanism didn't change the *symptom* at all, the endpoint
   itself was suspect, not just the auth details.
3. **Current approach**: FRITZ!Box's classic web UI does not use
   ``download.lua`` for TAM recordings on newer FRITZ!OS versions at all -
   it uses ``/cgi-bin/luacgi_notimeout`` with ``script=/lua/photo.lua`` and
   the recording's raw path as ``myabfile`` (this is also how FRITZ!Box
   serves e.g. photos/files from USB storage - ``photo.lua`` is a generic
   binary-file-serving script, not literally photo-specific). This was
   found via FHEM's mature ``72_FBTAM.pm`` module and independently
   corroborated by a real-world writeup (FRITZ!Box 7530, FRITZ!OS 7.57,
   https://kynan.github.io/blog/2023/12/28/save-all-voicebox-messages-from-your-fritzbox)
   describing the exact same endpoint. Both sources also agree the sid
   used must be the one embedded in the ``GetMessageList``/TAM response's
   own URL, not a separately-obtained classic-UI login sid - which would
   also explain why attempts 1 and 2 above failed even once a valid sid
   was being sent: a *different, unrelated* session than the one the box
   associated with the message list. See :meth:`FritzTam.get_download_url`.

This third approach is itself not yet confirmed against the user's actual
hardware - please open a GitHub issue (ideally with the resulting HTTP
status code) if it still fails.
"""

from __future__ import annotations

import datetime
import logging
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

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

# See the module docstring, download approach 3: the classic-web-UI
# endpoint actually used for TAM recordings on modern FRITZ!OS, and the
# sid regex used to pull the session id straight out of GetMessageList's
# own response URL (e.g. ".../tamcalllist.lua?sid=2400874c61e0ae6e&...").
_DOWNLOAD_PATH = "/cgi-bin/luacgi_notimeout"
_DOWNLOAD_SCRIPT = "/lua/photo.lua"
_SID_RE = re.compile(r"[?&]sid=([a-fA-F0-9]+)")


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
    ``Path`` (as delivered by the box, e.g.
    ``"/download.lua?path=/data/tam/rec/rec.0.009"`` - kept verbatim, NOT a
    directly-fetchable URL; see :meth:`FritzTam.get_download_url` for how
    the actual recording is downloaded), ``New`` ("1"/"0") and ``Count``.
    Lowercase convenience properties expose converted values: ``date``
    (datetime), ``duration`` (timedelta), ``new`` (bool).
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

    def get_download_url(self, message: TamMessage) -> str | None:
        """Build an authenticated download URL for one message's recording.

        See the module docstring (download approach 3) for why this is
        ``/cgi-bin/luacgi_notimeout?sid=...&script=/lua/photo.lua&myabfile=...``
        rather than the ``download.lua`` URL suggested by ``message.Path``
        itself, and why the sid is pulled fresh from a new
        ``GetMessageList`` call rather than reused/separately obtained: the
        sid the box accepts for a recording download appears to be tied to
        the specific session that produced the message list, not a
        general-purpose FRITZ!Box login.
        """
        if not message.Path:
            return None

        list_url = self._message_list_url()
        if not list_url:
            return None

        sid_match = _SID_RE.search(list_url)
        if not sid_match:
            _LOGGER.warning(
                "Anrufbeantworter: konnte keine sid aus der GetMessageList-"
                "Antwort-URL (%s) extrahieren - Download nicht möglich.",
                list_url,
            )
            return None
        sid = sid_match.group(1)

        # message.Path is normally "/download.lua?path=<raw file path>" -
        # pull just the raw path back out. Fall back to using message.Path
        # itself (minus any query string) if a FRITZ!OS version ever
        # delivers a bare path with no "download.lua?path=" wrapper.
        parsed = urlsplit(message.Path)
        raw_path = parse_qs(parsed.query).get("path", [None])[0] or parsed.path

        download_query = urlencode(
            {"sid": sid, "script": _DOWNLOAD_SCRIPT, "myabfile": raw_path}
        )
        return urljoin(list_url, f"{_DOWNLOAD_PATH}?{download_query}")
