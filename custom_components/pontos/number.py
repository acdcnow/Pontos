"""Number platform for the Pontos / SYR integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.components.number import NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import CONF_ENABLE_CONTROLS
from .const import DOMAIN
from .const import get_device_const
from .const import get_option
from .coordinator import PontosDataUpdateCoordinator
from .device import device_identifier
from .device import profile_limit

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the profile setting numbers of a device."""
    if not get_option(entry, CONF_ENABLE_CONTROLS):
        return

    device_const = get_device_const(entry)
    numbers: dict[str, dict[str, Any]] = getattr(device_const, "NUMBERS", {})
    if not numbers:
        return

    entry_data = hass.data[DOMAIN]["entries"][entry.entry_id]
    coordinator: PontosDataUpdateCoordinator = entry_data["coordinator"]
    identifier = device_identifier(entry_data["device_info"], entry)

    limit = profile_limit(device_const, coordinator)
    entities = [
        PontosNumber(
            entry, identifier, entry_data["device_info"], coordinator, key, config
        )
        for key, config in numbers.items()
        if config.get("profile", 0) <= limit
    ]

    LOGGER.debug("Creating %s profile setting entities", len(entities))
    async_add_entities(entities)


class PontosNumber(CoordinatorEntity[PontosDataUpdateCoordinator], NumberEntity):
    """A number entity that writes a value to a device endpoint."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        entry: ConfigEntry,
        identifier: str,
        device_info: dict[str, Any] | None,
        coordinator: PontosDataUpdateCoordinator,
        key: str,
        config: dict[str, Any],
    ) -> None:
        """Initialise the number entity."""
        super().__init__(coordinator)

        self._entry = entry
        self._device_info = device_info
        self._endpoint = config["endpoint"]
        self._profile = config["profile"]
        self._service = config["service"]
        self._field = config["field"]

        self._attr_name = config["name"]
        self._attr_unique_id = slugify(f"{identifier}_{key}")
        self._attr_native_unit_of_measurement = config.get("unit")
        self._attr_native_min_value = config.get("min", 0)
        self._attr_native_max_value = config.get("max", 100)
        self._attr_native_step = config.get("step", 1)
        self._attr_entity_category = config.get("entity_category")
        self._attr_native_value: float | None = None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return the device this entity belongs to."""
        return {"identifiers": self._device_info["identifiers"]}

    @property
    def available(self) -> bool:
        """Return True if the device reports this value."""
        return super().available and self._attr_native_value is not None

    async def async_added_to_hass(self) -> None:
        """Read the current value from the coordinator data."""
        await super().async_added_to_hass()
        self._update_value()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle new data from the coordinator."""
        self._update_value()
        super()._handle_coordinator_update()

    @callback
    def _update_value(self) -> None:
        """Convert the raw device value into a number."""
        raw_value = (self.coordinator.data or {}).get(self._endpoint)
        try:
            self._attr_native_value = float(str(raw_value).strip())
        except (TypeError, ValueError):
            self._attr_native_value = None

    async def async_set_native_value(self, value: float) -> None:
        """Send the new value to the device."""
        await self.hass.services.async_call(
            DOMAIN,
            self._service,
            {
                "entry_id": self._entry.entry_id,
                "profile": self._profile,
                self._field: int(value),
            },
            blocking=True,
        )
