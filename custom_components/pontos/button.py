"""Button platform for the Pontos / SYR integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
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
from .device import entity_device_info

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons of a device."""
    if not get_option(entry, CONF_ENABLE_CONTROLS):
        return

    buttons: dict[str, dict[str, Any]] = getattr(get_device_const(entry), "BUTTONS", {})
    if not buttons:
        return

    entry_data = hass.data[DOMAIN]["entries"][entry.entry_id]
    coordinator: PontosDataUpdateCoordinator = entry_data["coordinator"]
    identifier = device_identifier(entry_data["device_info"], entry)
    device_info = entity_device_info(entry_data["device_info"])

    async_add_entities(
        PontosServiceButton(entry, identifier, device_info, coordinator, key, config)
        for key, config in buttons.items()
    )


class PontosServiceButton(PontosControlEntity, ButtonEntity):
    """A button that sends one command to the device."""

    def __init__(
        self,
        entry: ConfigEntry,
        identifier: str,
        device_info: dict[str, Any],
        coordinator: PontosDataUpdateCoordinator,
        key: str,
        config: dict[str, Any],
    ) -> None:
        """Initialise the button."""
        super().__init__(entry, identifier, device_info, coordinator, key, config)
        self._service = config["service"]

    async def async_press(self) -> None:
        """Send the command of this button."""
        LOGGER.debug(
            "Button '%s' pressed, calling service %s", self._key, self._service
        )
        await self._call_service(self._service)
