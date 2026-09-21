"""Shared base for entities that mirror a device value and write it back.

The controls used to look up the sensor they mirror through the entity registry,
with a unique id built from the sensor name
(``slugify(f"{identifier}_{config['sensor']}")``).  That never matched the
unique id the sensor platform used, and the registry entry only exists once the
sensor platform has added its entities - ``button``/``select`` are set up before
``sensor``.  So the lookup failed: the entity logged
"Availability sensor ... not found" and stayed unavailable, which is why the
clear-alarms button and the profile dropdown were permanently greyed out.

Reading the value from the coordinator removes the dependency: no registry
lookup, no state listeners and no ordering between the platforms.
"""

from __future__ import annotations

import logging
import string
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .const import get_device_const
from .coordinator import PontosDataUpdateCoordinator

LOGGER = logging.getLogger(__name__)

#: What the devices report for a value that means "on".
TRUTHY_VALUES = frozenset({"1", "true", "on", "yes", "enabled", "active"})


def resolve_sensor(
    device_const: Any, reference: str | None
) -> tuple[str | None, dict[str, Any]]:
    """Return the sensor key and details of a sensor reference.

    The device configuration modules refer to the sensor a control mirrors
    either by its key (``"alarm_status"``) or by its name
    (``"Microleakage test schedule"``), so both spellings have to resolve.
    """
    if not reference:
        return None, {}

    details_map: dict[str, Any] = getattr(device_const, "SENSOR_DETAILS", {}) or {}
    if reference in details_map:
        return reference, details_map[reference] or {}

    for key, details in details_map.items():
        if (details or {}).get("name") == reference:
            return key, details

    LOGGER.warning(
        "Control mirrors the sensor '%s', which this device does not define",
        reference,
    )
    return None, {}


class PontosControlEntity(CoordinatorEntity[PontosDataUpdateCoordinator]):
    """Base class for a control that mirrors a single device value."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        identifier: str,
        device_info: dict[str, Any],
        coordinator: PontosDataUpdateCoordinator,
        key: str,
        config: dict[str, Any],
        unique_id_suffix: str = "",
    ) -> None:
        """Initialise the control entity."""
        super().__init__(coordinator)

        self._entry = entry
        self._identifier = identifier
        self._device_info = device_info
        self._key = key
        self._config = config
        self._device_const = get_device_const(entry)

        # The sensor whose value this control mirrors, if it has one.
        self._source_key, self._source_config = resolve_sensor(
            self._device_const,
            config.get("sensor") or config.get("availability_sensor"),
        )
        self._source_endpoint: str | None = self._source_config.get("endpoint")

        self._attr_translation_key = key
        self._attr_entity_category = config.get("entity_category")
        self._attr_unique_id = slugify(f"{identifier}_{key}{unique_id_suffix}")

    # ------------------------------------------------------------------
    # Entity properties
    # ------------------------------------------------------------------
    @property
    def device_info(self) -> dict[str, Any]:
        """Return the device this entity belongs to."""
        return self._device_info

    @property
    def available(self) -> bool:
        """Return True while the mirrored value can be read.

        A control without a source sensor (the clear-alarms button on the
        Pontos, for example) is available as soon as the device answers.
        """
        if not self._source_endpoint:
            return super().available

        return super().available and self._source_value() is not None

    # ------------------------------------------------------------------
    # The mirrored value
    # ------------------------------------------------------------------
    def _source_raw(self) -> Any:
        """Return the raw value of the mirrored endpoint."""
        if not self._source_endpoint:
            return None

        return (self.coordinator.data or {}).get(self._source_endpoint)

    def _source_value(self) -> str | None:
        """Return the value of the mirrored sensor, or None if unusable.

        The raw value is formatted the same way `sensor.py` formats it, so a
        control and its sensor always agree.
        """
        raw = self._source_raw()
        if raw is None:
            return None

        value = str(raw)
        if "ERROR" in value.upper():
            return None

        for old, new in (self._source_config.get("format_dict") or {}).items():
            value = value.replace(old, new)

        if code_dict := self._source_config.get("code_dict"):
            value = code_dict.get(value.upper(), value)

        return value.strip()

    def _source_number(self) -> float | None:
        """Return the mirrored value as a number, if it is one."""
        if (value := self._source_value()) is None:
            return None

        try:
            return float(value)
        except ValueError:
            return None

    def _source_bool(self) -> bool | None:
        """Return the mirrored value as a boolean, if it can be read."""
        if (value := self._source_value()) is None:
            return None

        return value.strip().lower() in TRUTHY_VALUES

    # ------------------------------------------------------------------
    # Writing to the device
    # ------------------------------------------------------------------
    def _endpoint_field(self, service: str) -> str | None:
        """Return the single placeholder of a service endpoint, if it has one."""
        service_config = getattr(self._device_const, "SERVICES", {}).get(service) or {}
        endpoint: str = service_config.get("endpoint", "")
        fields = [
            name
            for _, name, _, _ in string.Formatter().parse(endpoint)
            if name is not None
        ]
        return fields[0] if len(fields) == 1 else None

    async def _call_service(self, service: str, value: Any = None, **data: Any) -> None:
        """Call a service of this integration for this entry."""
        service_data: dict[str, Any] = {"entry_id": self._entry.entry_id, **data}
        if value is not None and (field := self._endpoint_field(service)):
            service_data[field] = value

        await self.hass.services.async_call(
            DOMAIN, service, service_data, blocking=True
        )
