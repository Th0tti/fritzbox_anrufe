"""The fritzbox_anrufe integration."""

import logging

from fritzconnection.core.exceptions import FritzConnectionException, FritzSecurityError
from requests.exceptions import ConnectionError as RequestsConnectionError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .base import FritzBoxPhonebook
from .const import CONF_PHONEBOOK, CONF_PREFIXES, PLATFORMS

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the fritzbox_anrufe integration from configuration.yaml (not used)."""
    return True

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up fritzbox_anrufe from a config entry."""
    base = FritzBoxPhonebook(
        hass,
        config_entry.data,
        config_entry.options,
        config_entry.entry_id,
    )
    await base.async_setup()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = base
    return True

async def async_unload_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Unloading the fritzbox_anrufe platforms."""
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

async def update_listener(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Update listener to reload after options change."""
    await hass.config_entries.async_reload(config_entry.entry_id)
