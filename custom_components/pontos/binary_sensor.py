"""Binary sensor platform for the Pontos / SYR integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .const import get_device_const
from .coordinator import PontosDataUpdateCoordinator
from .device import device_identifier

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors of a device."""
    device_const = get_device_const(entry)
    binary_sensors: dict[str, dict[str, Any]] = getattr(
        device_const, "BINARY_SENSORS", {}
    )
    if not binary_sensors:
        return

    entry_data = hass.data[DOMAIN]["entries"][entry.entry_id]
    coordinator: PontosDataUpdateCoordinator = entry_data["coordinator"]
    identifier = device_identifier(entry_data["device_info"], entry)

    async_add_entities(
        PontosBinarySensor(
            entry, identifier, entry_data["device_info"], coordinator, key, config
        )
        for key, config in binary_sensors.items()
    )


class PontosBinarySensor(
    CoordinatorEntity[PontosDataUpdateCoordinator], BinarySensorEntity
):
    """A binary sensor that is derived from a device endpoint."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        identifier: str,
        device_info: dict[str, Any] | None,
        coordinator: PontosDataUpdateCoordinator,
        key: str,
        config: dict[str, Any],
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator)

        self._entry = entry
        self._device_info = device_info
        self._key = key
        self._endpoint = config["endpoint"]
        self._code_dict = config.get("code_dict")
        self._on_values = {str(value).upper() for value in config.get("on_values", [])}
        self._off_values = {
            str(value).upper() for value in config.get("off_values", [])
        }

        self._attr_translation_key = key
        self._attr_unique_id = slugify(f"{identifier}_{key}")
        self._attr_device_class = config.get("device_class")
        self._attr_entity_category = config.get("entity_category")
        self._is_on: bool | None = None
        self._raw_value: Any = None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return the device this entity belongs to."""
        return {"identifiers": self._device_info["identifiers"]}

    @property
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return True if the device reported a usable value."""
        return super().available and self._is_on is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the raw device value and its meaning."""
        attributes: dict[str, Any] = {}

        if self._raw_value is not None:
            attributes["raw_value"] = self._raw_value

        if self._code_dict and self._raw_value is not None:
            attributes["status"] = self._code_dict.get(
                str(self._raw_value).upper(), str(self._raw_value)
            )

        return attributes or None

    async def async_added_to_hass(self) -> None:
        """Process the current coordinator data."""
        await super().async_added_to_hass()
        self._process()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle new data from the coordinator."""
        self._process()
        super()._handle_coordinator_update()

    @callback
    def _process(self) -> None:
        """Derive the on/off state from the raw device value."""
        raw_value = (self.coordinator.data or {}).get(self._endpoint)
        self._raw_value = raw_value
        self._is_on = None

        if raw_value is None:
            return

        value = str(raw_value).upper().strip()
        if "ERROR" in value:
            return

        if self._on_values:
            self._is_on = value in self._on_values
        elif self._off_values:
            self._is_on = value not in self._off_values
        else:
            LOGGER.error(
                "Binary sensor %s has neither on nor off values configured", self._key
            )
