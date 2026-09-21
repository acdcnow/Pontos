"""Select platform for the Pontos / SYR integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_ENABLE_CONTROLS
from .const import DOMAIN
from .const import get_device_const
from .const import get_option
from .control import PontosControlEntity
from .coordinator import PontosDataUpdateCoordinator
from .device import device_identifier
from .device import entity_device_info
from .profile_select import PontosProfileSelect

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the dropdowns of a device."""
    if not get_option(entry, CONF_ENABLE_CONTROLS):
        return

    selectors: dict[str, dict[str, Any]] = getattr(
        get_device_const(entry), "SELECTORS", {}
    )
    if not selectors:
        return

    entry_data = hass.data[DOMAIN]["entries"][entry.entry_id]
    coordinator: PontosDataUpdateCoordinator = entry_data["coordinator"]
    identifier = device_identifier(entry_data["device_info"], entry)
    # The dropdowns are settings, the profile selection is a control of the
    # meter itself, so they belong to different devices.
    device_info = entity_device_info(entry_data["device_info"])
    config_device_info = entry_data["config_device_info"]

    entities: list[SelectEntity] = []
    for key, config in selectors.items():
        if config.get("type") == "profile_select":
            entities.append(
                PontosProfileSelect(
                    entry,
                    identifier,
                    device_info,
                    coordinator,
                    key,
                    config,
                )
            )
        else:
            entities.append(
                PontosDropdownSelect(
                    entry, identifier, config_device_info, coordinator, key, config
                )
            )

    async_add_entities(entities)


class PontosDropdownSelect(PontosControlEntity, SelectEntity):
    """A dropdown that mirrors a device setting and writes it back.

    ``options`` maps the value the device expects onto the label it reports,
    for example ``{"1": "daily", "2": "weekly"}``.
    """

    def __init__(
        self,
        entry: ConfigEntry,
        identifier: str,
        device_info: dict[str, Any],
        coordinator: PontosDataUpdateCoordinator,
        key: str,
        config: dict[str, Any],
    ) -> None:
        """Initialise the dropdown."""
        super().__init__(
            entry, identifier, device_info, coordinator, key, config, "_select"
        )
        self._service = config["service"]
        # The device answers with the value, the user picks the label.
        self._labels: dict[str, str] = {
            str(code).strip(): str(label) for code, label in config["options"].items()
        }
        self._codes: dict[str, str] = {
            label: code for code, label in self._labels.items()
        }

    @property
    def options(self) -> list[str]:
        """Return the labels the device reports."""
        return list(self._labels.values())

    @property
    def current_option(self) -> str | None:
        """Return the option that matches the value the device reports."""
        if (raw := self._source_raw()) is not None:
            if (label := self._labels.get(str(raw).strip())) is not None:
                return label

        if (value := self._source_value()) is not None and value in self._codes:
            return value

        return None

    async def async_select_option(self, option: str) -> None:
        """Write the selected option to the device."""
        if (code := self._codes.get(str(option).strip())) is None:
            raise HomeAssistantError(f"'{option}' is not an option of {self._key}")

        LOGGER.debug(
            "Select '%s' set to '%s' (device value %s)", self._key, option, code
        )
        await self._call_service(self._service, code)
