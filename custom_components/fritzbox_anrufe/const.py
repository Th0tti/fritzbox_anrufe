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

UNKNOWN_NAME = "unknown"
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

CALL_TYPE_INCOMING = "eingehend"
CALL_TYPE_OUTGOING = "ausgehend"
CALL_TYPE_MISSED = "verpasst"

CALL_TYPES = (CALL_TYPE_INCOMING, CALL_TYPE_OUTGOING, CALL_TYPE_MISSED)

# Konfigurierbare Verlaufstiefe der Anruflisten-Sensoren (Options-Flow)
CONF_CALL_LOG_LIMIT_TYPE = "call_log_limit_type"
CONF_CALL_LOG_COUNT = "call_log_count"
CONF_CALL_LOG_DAYS = "call_log_days"

CALL_LOG_LIMIT_COUNT: Final = "count"
CALL_LOG_LIMIT_DAYS: Final = "days"

DEFAULT_CALL_LOG_LIMIT_TYPE = CALL_LOG_LIMIT_COUNT
DEFAULT_CALL_LOG_COUNT = 20
DEFAULT_CALL_LOG_DAYS = 7

MIN_CALL_LOG_COUNT = 1
MAX_CALL_LOG_COUNT = 200
MIN_CALL_LOG_DAYS = 1
MAX_CALL_LOG_DAYS = 90
