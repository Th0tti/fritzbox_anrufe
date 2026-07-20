"""Constants for the AVM Fritz!Box call monitor integration."""

from enum import StrEnum
from typing import Final

from homeassistant.const import Platform


class FritzState(StrEnum):
    """Fritz!Box call states."""

    RING = "RING"
    CALL = "CALL"
    CONNECT = "CONNECT"
    DISCONNECT = "DISCONNECT"


ATTR_PREFIXES = "prefixes"

FRITZ_ATTR_NAME = "name"
FRITZ_ATTR_SERIAL_NUMBER = "Serial"

# Anzeigename für Anrufer/Angerufene ohne Telefonbuch-Eintrag - erscheint
# so direkt in Sensor-Attributen (calls[].name, Live-Attribute from_name/
# to_name/with_name) und damit auch in der Dashboard-Karte.
UNKNOWN_NAME = "Unbekannt"
SERIAL_NUMBER = "serial_number"
REGEX_NUMBER = r"[^\d\+]"

CONF_PHONEBOOK = "phonebook"
CONF_PHONEBOOK_NAME = "phonebook_name"
CONF_PREFIXES = "prefixes"

DEFAULT_HOST = "169.254.1.1"  # IP valid for all Fritz!Box routers
DEFAULT_PORT = 1012
DEFAULT_USERNAME = "admin"
DEFAULT_PHONEBOOK = 0
DEFAULT_NAME = "Phone"

DOMAIN: Final = "fritzbox_anrufe"
MANUFACTURER: Final = "FRITZ!"

PLATFORMS = [Platform.SENSOR]

# --- Anruflisten-Verlaufssensoren (fritzbox_anrufe_eingehend/ausgehend/verpasst) ---
# sowie der Live-Callmonitor-Sensor (fritzbox_anrufe_live). Diese Suffixe
# werden nur für den *translation_key* (übersetzter Anzeigename + Icon)
# verwendet, nicht für die technische entity_id - siehe Kommentar in
# sensor.py für Details, warum Home Assistant das nicht anders unterstützt.

CALL_TYPE_INCOMING = "eingehend"
CALL_TYPE_OUTGOING = "ausgehend"
CALL_TYPE_MISSED = "verpasst"
CALL_TYPE_LIVE = "live"

CALL_TYPES = (CALL_TYPE_INCOMING, CALL_TYPE_OUTGOING, CALL_TYPE_MISSED)

# --- Anrufbeantworter-Sensor (fritzbox_anrufe_anrufbeantworter) - EXPERIMENTELL ---
# Deckt nur Anrufbeantworter/Sprachnachrichten ab, bewusst kein Fax (siehe
# tam.py/voicemail.py). Kein Bestandteil von CALL_TYPES, da dieser Sensor
# keine eigene Anzahl/Tage-Verlaufskonfiguration hat (siehe config_flow.py).
CALL_TYPE_VOICEMAIL = "anrufbeantworter"

# Basis-URL des authentifizierten HTTP-Proxys, über den Anrufbeantworter-
# Aufnahmen im Dashboard abgespielt werden (siehe http.py). Vollständiger
# Pfad: f"{TAM_MEDIA_URL_BASE}/{config_entry_id}/{message_index}".
TAM_MEDIA_URL_BASE = "/api/fritzbox_anrufe/tam_media"

# Analoge Proxy-Route für Sprachnachrichten, die über einen Eintrag der
# Anruflisten-Sensoren (nicht über den Anrufbeantworter-Sensor) erreicht
# werden - siehe http.py:FritzBoxCallMediaView und die "Weiterverarbeitung"
# in der Dashboard-Karte (CALL_OUTCOME_VOICEMAIL). Vollständiger Pfad:
# f"{CALL_MEDIA_URL_BASE}/{config_entry_id}/{call_type}/{call_id}".
CALL_MEDIA_URL_BASE = "/api/fritzbox_anrufe/call_media"

# --- "Weiterverarbeitung" (optionale Zusatzzeile pro Anruf in der Karte) --
# Klassifiziert, wie ein einzelner Anruf ausgegangen ist - zusätzlich zur
# (weiterhin bestehenden) Zuordnung zu genau einem der drei
# Anruflisten-Sensoren (eingehend/ausgehend/verpasst). Siehe call_log.py
# für die Klassifizierungslogik und ihre Grenzen (Fehlerbehebung in der
# README).
#
# Eingehend: nur "beantwortet" möglich (per Person angenommen) - Anrufe,
# die zum Anrufbeantworter gingen oder abgewiesen wurden, zählen seit
# Version 1.0.3 komplett als "verpasst", nicht mehr als "eingehend".
CALL_OUTCOME_ANSWERED = "beantwortet"
# Verpasst: mit aufgenommener Nachricht (Path vorhanden) ODER ohne - die
# FRITZ!Box-Anrufliste unterscheidet nicht zuverlässig zwischen "vor dem
# Anrufbeantworter aufgelegt" und "Anrufbeantworter war nicht aktiv/
# erreichbar"; beide fallen unter CALL_OUTCOME_UNREACHED, bis echte
# Testdaten eine feinere Unterscheidung erlauben (siehe README).
CALL_OUTCOME_VOICEMAIL = "anrufbeantworter"
CALL_OUTCOME_UNREACHED = "nicht_erreicht"
# Ausgehend: nur Verbindungsdauer > 0 ist zuverlässig auswertbar - eine
# Unterscheidung zwischen "besetzt" und "niemand nimmt ab" liefert die
# FRITZ!Box-Anrufliste nicht (siehe README, Fehlerbehebung).
CALL_OUTCOME_CONNECTED = "verbunden"
CALL_OUTCOME_NOT_CONNECTED = "nicht_verbunden"

# Konfigurierbare Verlaufstiefe der drei Anruflisten-Sensoren - jeder Typ
# (eingehend/ausgehend/verpasst) hat seine EIGENEN, unabhängig einstellbaren
# Optionen (Options-Flow UND bereits bei der Erst-Einrichtung).
CALL_LOG_LIMIT_COUNT: Final = "count"
CALL_LOG_LIMIT_DAYS: Final = "days"

DEFAULT_CALL_LOG_LIMIT_TYPE = CALL_LOG_LIMIT_COUNT
DEFAULT_CALL_LOG_COUNT = 10
DEFAULT_CALL_LOG_DAYS = 7

MIN_CALL_LOG_DAYS = 1
MAX_CALL_LOG_DAYS = 90

# Feste Auswahlwerte für das "Anzahl"-Dropdown (pro Sensor).
CALL_LOG_COUNT_PRESETS: Final[tuple[int, ...]] = (5, 10, 20, 50, 100, 200)

# Wie viele Tage Rohdaten (alle Anruftypen gemischt) pro Aktualisierung von
# der FRITZ!Box geladen werden, bevor sie clientseitig je Sensor nach dessen
# eigener Einstellung (Anzahl oder Tage) gefiltert werden. Die FRITZ!Box/
# fritzconnection-API kennt keinen "letzte N Anrufe von Typ X"-Parameter,
# sondern begrenzt immer den gemischten Gesamtabruf - siehe call_log.py.
SHARED_CALL_LOG_FETCH_DAYS: Final = MAX_CALL_LOG_DAYS


def conf_call_log_limit_type(call_type: str) -> str:
    """Options-Key: Anzahl- oder Tage-Modus für einen Anruflisten-Sensor."""
    return f"call_log_limit_type_{call_type}"


def conf_call_log_count(call_type: str) -> str:
    """Options-Key: max. Anzahl Einträge für einen Anruflisten-Sensor."""
    return f"call_log_count_{call_type}"


def conf_call_log_days(call_type: str) -> str:
    """Options-Key: Tage-Fenster für einen Anruflisten-Sensor."""
    return f"call_log_days_{call_type}"
