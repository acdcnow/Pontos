"""Time platform for the Pontos / SYR integration."""

from __future__ import annotations

import logging
from datetime import datetime
from datetime import time as dtime
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_ENABLE_CONTROLS
from .const import DOMAIN
from .const import get_device_const
from .const import get_option
from .control import PontosControlEntity
from .coordinator import PontosDataUpdateCoordinator
from .device import device_identifier

LOGGER = logging.getLogger(__name__)

#: Formats the devices report a time in.
TIME_FORMATS = ("%H:%M", "%H:%M:%S")


def parse_time(value: str) -> dtime | None:
    """Return the time a device value represents, if any."""
    text = value.strip()

    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue

    # Some devices report the time as digits only ("815" or "0815").
    if text.isdigit() and 3 <= len(text) <= 4:
        hours = int(text[:-2])
        minutes = int(text[-2:])
        if hours < 24 and minutes < 60:
            return dtime(hour=hours, minute=minutes)

    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the time settings of a device."""
    if not get_option(entry, CONF_ENABLE_CONTROLS):
        return

    times: dict[str, dict[str, Any]] = getattr(
        get_device_const(entry), "TIME_ENTRIES", {}
    )
    if not times:
        return

    entry_data = hass.data[DOMAIN]["entries"][entry.entry_id]
    coordinator: PontosDataUpdateCoordinator = entry_data["coordinator"]
    identifier = device_identifier(entry_data["device_info"], entry)
    # The times are settings, so they belong to the configuration device.
    device_info = entry_data["config_device_info"]

    async_add_entities(
        PontosTimeEntry(entry, identifier, device_info, coordinator, key, config)
        for key, config in times.items()
    )


class PontosTimeEntry(PontosControlEntity, TimeEntity):
    """A device time that mirrors a sensor and calls a service when set."""

    def __init__(
        self,
        entry: ConfigEntry,
        identifier: str,
        device_info: dict[str, Any],
        coordinator: PontosDataUpdateCoordinator,
        key: str,
        config: dict[str, Any],
    ) -> None:
        """Initialise the time entity."""
        super().__init__(
            entry, identifier, device_info, coordinator, key, config, "_time"
        )
        self._service = config["service"]

    @property
    def native_value(self) -> dtime | None:
        """Return the time the device reports."""
        value = self._source_value()
        if value is None:
            return None

        if (parsed := parse_time(value)) is None:
            LOGGER.warning(
                "Time setting '%s' got the value '%s', which is not a time",
                self._key,
                value,
            )
        return parsed

    async def async_set_value(self, value: dtime) -> None:
        """Write the new time to the device."""
        if isinstance(value, str):  # the frontend always sends a time object
            if (parsed := parse_time(str(value))) is None:
                LOGGER.error("Time setting '%s' got '%s'", self._key, value)
                return
            value = parsed

        time_str = value.strftime("%H:%M")
        LOGGER.debug("Time setting '%s' set to %s", self._key, time_str)
        await self._call_service(self._service, time_str)
