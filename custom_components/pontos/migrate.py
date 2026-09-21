"""Config entry migrations for the Pontos integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_NAME
from .const import CONF_FETCH_INTERVAL
from .const import CONF_IP_ADDRESS
from .const import CONF_MAKE
from .const import CONF_PORT
from .const import DEFAULT_MAKE
from .const import DEFAULT_PORT
from .const import normalise_options

LOGGER = logging.getLogger(__name__)

#: Keep in sync with `PontosConfigFlow.VERSION`.
CONFIG_ENTRY_VERSION = 5


async def migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate an old config entry to the current data and options layout."""
    if config_entry.version > CONFIG_ENTRY_VERSION:
        # The entry was created by a newer version of the integration, do not
        # touch it.
        LOGGER.error(
            "Config entry '%s' has version %s, but this integration only supports"
            " up to version %s",
            config_entry.title,
            config_entry.version,
            CONFIG_ENTRY_VERSION,
        )
        return False

    version = config_entry.version
    data = dict(config_entry.data)
    options = dict(config_entry.options)

    if version < 2 and CONF_MAKE not in data:
        data[CONF_MAKE] = DEFAULT_MAKE

    if version < 3 and CONF_FETCH_INTERVAL not in data:
        data[CONF_FETCH_INTERVAL] = 10

    if version < 4:
        # Connection settings moved from data to options.
        if (fetch_interval := data.pop(CONF_FETCH_INTERVAL, None)) is not None:
            options.setdefault(CONF_FETCH_INTERVAL, fetch_interval)
        if (ip_address := data.pop(CONF_IP_ADDRESS, None)) is not None:
            options.setdefault(CONF_IP_ADDRESS, ip_address)

    if version < 5:
        # 2.9.3: the domain changed to `pontos` (handled by the config flow) and
        # the new options were introduced.
        data.setdefault(CONF_DEVICE_NAME, config_entry.title)
        options.setdefault(CONF_PORT, DEFAULT_PORT)
        options = normalise_options(options)

    if (
        data != dict(config_entry.data)
        or options != dict(config_entry.options)
        or version != CONFIG_ENTRY_VERSION
    ):
        hass.config_entries.async_update_entry(
            config_entry,
            data=data,
            options=options,
            version=CONFIG_ENTRY_VERSION,
        )
        LOGGER.info(
            "Migrated config entry '%s' from version %s to %s",
            config_entry.title,
            version,
            CONFIG_ENTRY_VERSION,
        )

    return True
