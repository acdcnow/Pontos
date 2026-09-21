"""The Pontos / SYR water meter integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_DEBUG_LOGGING
from .const import DOMAIN
from .const import MAKES
from .const import get_make
from .const import get_option
from .coordinator import PontosDataUpdateCoordinator
from .device import configuration_device_info
from .device import register_device
from .migrate import migrate_entry
from .services import async_unregister_services
from .services import async_register_services

LOGGER = logging.getLogger(__name__)

#: Number of currently setup entries per integration logger state.
_DEBUG_COUNTERS: dict[int, int] = {}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Pontos device from a config entry."""
    device_const = MAKES[get_make(entry)]

    coordinator = PontosDataUpdateCoordinator(hass, entry, device_const)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("entries", {})[entry.entry_id] = {
        "entry": entry,
        "coordinator": coordinator,
        "device_info": None,
        "device_id": None,
        "config_device_info": None,
        "command_lock": coordinator.lock,
    }

    try:
        await register_device(hass, entry, coordinator)
    except Exception as err:  # noqa: BLE001 - surfaced as a failed setup
        LOGGER.error("Error setting up device: %s", err)
        hass.data[DOMAIN]["entries"].pop(entry.entry_id, None)
        raise ConfigEntryNotReady(f"Could not read device information: {err}") from err

    # The settings (profile limits, profile selection, ...) belong to their own
    # device so the meter device stays about its measurements.
    entry_data = hass.data[DOMAIN]["entries"][entry.entry_id]
    entry_data["config_device_info"] = configuration_device_info(
        entry, entry_data["device_info"], entry_data["device_id"]
    )

    await async_register_services(hass)

    # Options changed by the user require a new coordinator (new IP, interval,
    # timeout, unit, ...), so reload the entry.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    if get_option(entry, CONF_DEBUG_LOGGING):
        _async_enable_debug_logging()

    platforms = getattr(device_const, "PLATFORMS", [])
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    device_const = MAKES[get_make(entry)]
    platforms = getattr(device_const, "PLATFORMS", [])

    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)

    if not unload_ok:
        return False

    entries: dict = hass.data.get(DOMAIN, {}).get("entries", {})
    entries.pop(entry.entry_id, None)

    if not entries:
        await async_unregister_services(hass)

    if get_option(entry, CONF_DEBUG_LOGGING):
        _async_disable_debug_logging()

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up after the entry has been removed."""
    entries: dict = hass.data.get(DOMAIN, {}).get("entries", {})
    if not entries:
        await async_unregister_services(hass)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry (used by the options update listener)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate an old config entry to the current data/options format."""
    return await migrate_entry(hass, config_entry)


# ---------------------------------------------------------------------------
# Debug logging helpers
# ---------------------------------------------------------------------------
async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    await hass.config_entries.async_reload(entry.entry_id)


def _integration_loggers() -> list[logging.Logger]:
    """Return the loggers used by this integration."""
    return [
        logging.getLogger(__name__),
        logging.getLogger(__package__),
    ]


def _async_enable_debug_logging() -> None:
    """Turn on debug logging for this integration."""
    for logger in _integration_loggers():
        _DEBUG_COUNTERS[logger.name] = _DEBUG_COUNTERS.get(logger.name, 0) + 1
        logger.setLevel(logging.DEBUG)


def _async_disable_debug_logging() -> None:
    """Restore the default log level of this integration."""
    for logger in _integration_loggers():
        count = _DEBUG_COUNTERS.get(logger.name, 0) - 1
        if count > 0:
            _DEBUG_COUNTERS[logger.name] = count
            continue

        _DEBUG_COUNTERS.pop(logger.name, None)
        logger.setLevel(logging.NOTSET)
