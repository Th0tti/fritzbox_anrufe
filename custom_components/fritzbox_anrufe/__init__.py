"""The fritzbox_anrufe integration."""

from dataclasses import dataclass
import logging

from fritzconnection.core.exceptions import FritzConnectionException, FritzSecurityError
from fritzconnection.lib.fritzcall import FritzCall
from requests.exceptions import ConnectionError as RequestsConnectionError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .base import FritzBoxPhonebook
from .call_log import FritzCallLogCoordinator
from .const import CONF_PHONEBOOK, CONF_PREFIXES, PLATFORMS

_LOGGER = logging.getLogger(__name__)


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
