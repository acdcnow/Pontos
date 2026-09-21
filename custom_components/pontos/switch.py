"""Switch platform for the Pontos / SYR integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches of a device."""
    if not get_option(entry, CONF_ENABLE_CONTROLS):
        return

    switches: dict[str, dict[str, Any]] = getattr(
        get_device_const(entry), "SWITCHES", {}
    )
    if not switches:
        return

    entry_data = hass.data[DOMAIN]["entries"][entry.entry_id]
    coordinator: PontosDataUpdateCoordinator = entry_data["coordinator"]
    identifier = device_identifier(entry_data["device_info"], entry)
    # The switches are settings, so they belong to the configuration device.
    device_info = entry_data["config_device_info"]

    async_add_entities(
        PontosSwitch(entry, identifier, device_info, coordinator, key, config)
        for key, config in switches.items()
    )


class PontosSwitch(PontosControlEntity, SwitchEntity):
    """A switch that mirrors a device setting and writes it back."""

    def __init__(
        self,
        entry: ConfigEntry,
        identifier: str,
        device_info: dict[str, Any],
        coordinator: PontosDataUpdateCoordinator,
        key: str,
        config: dict[str, Any],
    ) -> None:
        """Initialise the switch."""
        super().__init__(
            entry, identifier, device_info, coordinator, key, config, "_switch"
        )
        self._service_on = config["service_on"]
        self._service_off = config["service_off"]

    @property
    def is_on(self) -> bool | None:
        """Return the state the device reports."""
        return self._source_bool()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        LOGGER.debug("Turning switch '%s' on", self._key)
        await self._call_service(self._service_on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        LOGGER.debug("Turning switch '%s' off", self._key)
        await self._call_service(self._service_off)
