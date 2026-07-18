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
from homeassistant.helpers import entity_registry as er

from .base import FritzBoxPhonebook
from .call_log import FritzCallLogCoordinator
from .const import (
    CALL_TYPE_INCOMING,
    CALL_TYPE_LIVE,
    CALL_TYPE_MISSED,
    CALL_TYPE_OUTGOING,
    CALL_TYPE_VOICEMAIL,
    CONF_PHONEBOOK,
    CONF_PREFIXES,
    DOMAIN,
    PLATFORMS,
    SERIAL_NUMBER,
)
from .http import FritzBoxTamMediaView
from .tam import FritzTam
from .voicemail import FritzTamCoordinator

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


# --- Anrufbeantworter-Audio-Proxy (EXPERIMENTELL, siehe tam.py) ------------
_TAM_VIEW_REGISTERED_KEY = f"{DOMAIN}_tam_view_registered"


def _async_register_tam_view(hass: HomeAssistant) -> None:
    """Register the authenticated TAM-audio proxy view, at most once."""
    if hass.data.get(_TAM_VIEW_REGISTERED_KEY):
        return
    hass.data[_TAM_VIEW_REGISTERED_KEY] = True
    hass.http.register_view(FritzBoxTamMediaView())


def _async_reserve_entity_ids(hass: HomeAssistant, config_entry: ConfigEntry, unique_id: str) -> None:
    """Reserve fixed, language-neutral entity_ids for the fritzbox_anrufe sensors.

    Home Assistant computes an entity's entity_id from its (translated,
    therefore language-dependent) display name and offers no supported hook
    on the entity itself to override that - `Entity.suggested_object_id` is
    a read-only property, there is no `_attr_suggested_object_id`.

    What Home Assistant *does* support: once an entity-registry entry for a
    given (domain, platform, unique_id) exists, the entity platform never
    recomputes its entity_id - it just reuses whatever is already
    registered. So we pre-create the registry entries here, before the
    sensor platform sets up, passing our own fixed `suggested_object_id`.
    This only affects entities that don't already have a registry entry
    (fresh installs, or after an entity was deleted) - already-registered
    entities keep their current entity_id untouched, exactly like a manual
    rename would (Settings -> Devices & Services -> Entities -> gear icon
    -> "Entity ID"). With more than one FRITZ!Box account configured, the
    second/third account's sensors get "_2"/"_3" suffixes, same as any
    other Home Assistant entity_id collision.
    """
    registry = er.async_get(hass)
    reservations = {
        unique_id: f"{DOMAIN}_{CALL_TYPE_LIVE}",
        f"{unique_id}-{CALL_TYPE_INCOMING}": f"{DOMAIN}_{CALL_TYPE_INCOMING}",
        f"{unique_id}-{CALL_TYPE_OUTGOING}": f"{DOMAIN}_{CALL_TYPE_OUTGOING}",
        f"{unique_id}-{CALL_TYPE_MISSED}": f"{DOMAIN}_{CALL_TYPE_MISSED}",
        f"{unique_id}-{CALL_TYPE_VOICEMAIL}": f"{DOMAIN}_{CALL_TYPE_VOICEMAIL}",
    }
    for sensor_unique_id, suggested_object_id in reservations.items():
        registry.async_get_or_create(
            "sensor",
            DOMAIN,
            sensor_unique_id,
            suggested_object_id=suggested_object_id,
            config_entry=config_entry,
        )


@dataclass
class FritzBoxRuntimeData:
    """Runtime data shared between the live call-monitor sensor, the

    call-list history sensors (fritzbox_anrufe_eingehend/ausgehend/verpasst)
    and the (experimental) answering-machine sensor (fritzbox_anrufe_anrufbeantworter).
    """

    phonebook: FritzBoxPhonebook
    call_log_coordinator: FritzCallLogCoordinator
    tam_coordinator: FritzTamCoordinator | None = None


type FritzBoxCallMonitorConfigEntry = ConfigEntry[FritzBoxRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, config_entry: FritzBoxCallMonitorConfigEntry
) -> bool:
    """Set up the fritzbox_anrufe platforms."""
    await _async_register_frontend_card(hass)
    _async_register_tam_view(hass)

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

    # Anrufbeantworter (EXPERIMENTELL, siehe tam.py/voicemail.py). Same
    # "never block setup, just show as unavailable" treatment as the call
    # list above - a missing permission or an unconfirmed TR-064 API shape
    # on the user's FRITZ!Box must not break the rest of the integration.
    fritz_tam = FritzTam(fc=fritzbox_phonebook.fph.fc)
    tam_coordinator = FritzTamCoordinator(hass, config_entry, fritz_tam)
    await tam_coordinator.async_refresh()

    unique_id = f"{config_entry.data[SERIAL_NUMBER]}-{config_entry.data[CONF_PHONEBOOK]}"
    _async_reserve_entity_ids(hass, config_entry, unique_id)

    config_entry.runtime_data = FritzBoxRuntimeData(
        phonebook=fritzbox_phonebook,
        call_log_coordinator=call_log_coordinator,
        tam_coordinator=tam_coordinator,
    )
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: FritzBoxCallMonitorConfigEntry
) -> bool:
    """Unloading the fritzbox_anrufe platforms."""
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
