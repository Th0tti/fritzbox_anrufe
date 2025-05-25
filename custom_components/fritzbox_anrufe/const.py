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
FRITZ_ATTR_VIP = "vip"
FRITZ_ATTR_NUMBER = "number"
FRITZ_ATTR_DEVICE = "device"
FRITZ_ATTR_ACCEPTED = "accepted"
FRITZ_ATTR_CLOSED = "closed"
FRITZ_ATTR_DURATION = "duration"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_PHONEBOOK = "phonebook"
CONF_PHONEBOOK_NAME = "phonebook_name"
CONF_PREFIXES = "prefixes"

DEFAULT_HOST = "169.254.1.1"  # IP valid for all Fritz!Box routers
DEFAULT_PORT = 1012
DEFAULT_USERNAME = "admin"
DEFAULT_PHONEBOOK = 0
DEFAULT_NAME = "Phone"

DOMAIN: Final = "fritzbox_anrufe"
MANUFACTURER: Final = "AVM"

PLATFORMS = [Platform.SENSOR]
