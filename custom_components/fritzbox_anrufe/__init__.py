"""The fritzbox_anrufe integration."""

from dataclasses import dataclass
import logging
from pathlib import Path

from fritzconnection.core.exceptions import FritzConnectionException, FritzSecurityError
from fritzconnection.lib.fritzcall import FritzCall
from requests.exceptions import ConnectionError as RequestsConnectionError

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .base import FritzBoxPhonebook
from .call_log import FritzCallLogCoordinator
from .const import CONF_PHONEBOOK, CONF_PREFIXES, DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

# --- Bundled Lovelace card (fritzbox-anrufe-card.js) -----------------------
#
# Served directly from this integration's "www" folder and injected into
# every dashboard automatically via add_extra_js_url(), so users do not have
# to register a Lovelace resource by hand. See www/fritzbox-anrufe-card.js.
_CARD_URL_BASE = "/fritzbox_anrufe_files"
_CARD_FILENAME = "fritzbox-anrufe-card.js"
_CARD_DIR = Path(__file__).parent / "www"
_FRONTEND_REGISTERED_KEY = f"{DOMAIN}_frontend_registered"


async def _async_register_frontend_card(hass: HomeAssistant) -> None:
    """Serve and register the bundled fritzbox-anrufe-card Lovelace card.

    Idempotent / runs at most once per Home Assistant instance, even if
    multiple FRITZ!Box accounts (config entries) are set up.
    """
    if hass.data.get(_FRONTEND_REGISTERED_KEY):
        return
    hass.data[_FRONTEND_REGISTERED_KEY] = True

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(_CARD_URL_BASE, str(_CARD_DIR), False)]
        )
    except RuntimeError:
        # Already registered (e.g. integration reloaded without a full HA
        # restart) - safe to ignore, the static path is still serving.
        _LOGGER.debug("Static path for %s already registered", _CARD_URL_BASE)

    add_extra_js_url(hass, f"{_CARD_URL_BASE}/{_CARD_FILENAME}")


@dataclass
class FritzBoxRuntimeData:
    """Runtime data shared between the live call-monitor sensor and the

    call-list history sensors (fritzbox_anrufe_eingehend/ausgehend/verpasst).
    """

    phonebook: FritzBoxPhonebook
    call_log_coordinator: FritzCallLogCoordinator


type FritzBoxCallMonitorConfigEntry = ConfigEntry[FritzBoxRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, config_entry: FritzBoxCallMonitorConfigEntry
) -> bool:
    """Set up the fritzbox_anrufe platforms."""
    await _async_register_frontend_card(hass)

    fritzbox_phonebook = FritzBoxPhonebook(
        host=config_entry.data[CONF_HOST],
        username=config_entry.data[CONF_USERNAME],
        password=config_entry.data[CONF_PASSWORD],
        phonebook_id=config_entry.data[CONF_PHONEBOOK],
        prefixes=config_entry.options.get(CONF_PREFIXES),
    )

    try:
        await hass.async_add_executor_job(fritzbox_phonebook.init_phonebook)
    except FritzSecurityError as ex:
        _LOGGER.error(
            (
                "User has insufficient permissions to access FRITZ!Box settings and"
                " its phonebooks: %s"
            ),
            ex,
        )
        return False
    except FritzConnectionException as ex:
        raise ConfigEntryAuthFailed from ex
    except RequestsConnectionError as ex:
        _LOGGER.error("Unable to connect to FRITZ!Box call monitor: %s", ex)
        raise ConfigEntryNotReady from ex

    # Reuse the already-authenticated TR-064 connection opened for the
    # phonebook lookup instead of opening a second one just for the call list.
    fritz_call = FritzCall(fc=fritzbox_phonebook.fph.fc)
    call_log_coordinator = FritzCallLogCoordinator(hass, config_entry, fritz_call)
    # Deliberately not using async_config_entry_first_refresh() here: a
    # missing "Anrufliste" permission or disabled TR-064 on the FRITZ!Box
    # account must not prevent the whole integration (incl. the working
    # call-monitor sensor) from loading. The three history sensors simply
    # stay "unavailable" until the coordinator can fetch data successfully.
    await call_log_coordinator.async_refresh()

    config_entry.runtime_data = FritzBoxRuntimeData(
        phonebook=fritzbox_phonebook,
        call_log_coordinator=call_log_coordinator,
    )
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: FritzBoxCallMonitorConfigEntry
) -> bool:
    """Unloading the fritzbox_anrufe platforms."""
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
