"""Sensor platform for the Pontos / SYR integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import RestoreSensor
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from homeassistant.util.dt import utcnow

from .const import CONF_ENABLE_DIAGNOSTICS
from .const import CONF_IGNORE_INVALID_VALUES
from .const import CONF_STALE_TOLERANCE
from .const import CONF_VOLUME_UNIT
from .const import DEFAULT_VOLUME_UNIT
from .const import DOMAIN
from .const import get_device_const
from .const import get_option
from .coordinator import PontosDataUpdateCoordinator
from .device import device_identifier
from .device import profile_limit

LOGGER = logging.getLogger(__name__)

DISPLAY_UNITS = {
    UnitOfVolume.LITERS.value: UnitOfVolume.LITERS,
    UnitOfVolume.CUBIC_METERS.value: UnitOfVolume.CUBIC_METERS,
}

#: Device classes whose value is a volume and can be converted for display.
VOLUME_DEVICE_CLASSES = {SensorDeviceClass.WATER, SensorDeviceClass.VOLUME}


def _to_number(value: Any) -> float | None:
    """Convert a device value to a float, returning None if that is not possible."""
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _profile_number(key: str) -> int | None:
    """Return the profile number of a `profile_<n>` sensor key."""
    if not key.startswith("profile_"):
        return None

    number = key.removeprefix("profile_")
    return int(number) if number.isdigit() else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors of a device."""
    device_const = get_device_const(entry)
    entry_data = hass.data[DOMAIN]["entries"][entry.entry_id]
    coordinator: PontosDataUpdateCoordinator = entry_data["coordinator"]
    device_info = entry_data["device_info"]
    identifier = device_identifier(device_info, entry)
    include_diagnostics = get_option(entry, CONF_ENABLE_DIAGNOSTICS)
    limit = profile_limit(device_const, coordinator)

    entities: list[PontosSensor] = []
    for key, sensor_config in device_const.SENSOR_DETAILS.items():
        if not include_diagnostics and sensor_config.get("entity_category") is not None:
            continue

        if (profile := _profile_number(key)) is not None and profile > limit:
            # The device does not have this profile
            continue

        entities.append(
            PontosSensor(entry, identifier, device_info, coordinator, key, sensor_config)
        )

    async_add_entities(entities)


class PontosSensor(CoordinatorEntity[PontosDataUpdateCoordinator], RestoreSensor):
    """A sensor that mirrors a single device endpoint."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        identifier: str,
        device_info: dict[str, Any] | None,
        coordinator: PontosDataUpdateCoordinator,
        key: str,
        sensor_config: dict[str, Any],
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)

        self._entry = entry
        self._key = key
        self._config = sensor_config
        self._device_info = device_info
        self._endpoint = sensor_config["endpoint"]
        self._format_dict = sensor_config.get("format_dict")
        self._code_dict = sensor_config.get("code_dict")
        self._scale = sensor_config.get("scale")
        self._attributes = sensor_config.get("attributes", {})

        self._attr_translation_key = key
        self._attr_unique_id = slugify(f"{identifier}_{sensor_config['name']}")
        self._attr_native_unit_of_measurement = sensor_config.get("unit")
        self._attr_device_class = sensor_config.get("device_class")
        self._attr_entity_category = sensor_config.get("entity_category")
        self._attr_state_class = sensor_config.get("state_class")

        # A sensor that declares a device class, a state class or a unit is
        # expected to report a number.
        self._is_numeric = sensor_config.get(
            "numeric",
            any(
                (
                    sensor_config.get("unit"),
                    sensor_config.get("device_class"),
                    sensor_config.get("state_class"),
                    sensor_config.get("scale") is not None,
                )
            ),
        )
        self._min_value = sensor_config.get("min_value")
        if self._min_value is None and self._attr_state_class in (
            SensorStateClass.TOTAL,
            SensorStateClass.TOTAL_INCREASING,
        ):
            # A cumulative meter can never count backwards, so implausible
            # values (e.g. the -1 some devices report while starting up) must
            # never reach the recorder.
            self._min_value = 0
        self._ignore_invalid = get_option(entry, CONF_IGNORE_INVALID_VALUES)
        self._stale_tolerance = get_option(entry, CONF_STALE_TOLERANCE)

        if (
            self._attr_device_class in VOLUME_DEVICE_CLASSES
            and get_option(entry, CONF_VOLUME_UNIT) != DEFAULT_VOLUME_UNIT
        ):
            self._attr_suggested_unit_of_measurement = DISPLAY_UNITS.get(
                get_option(entry, CONF_VOLUME_UNIT)
            )

        self._raw_value: Any = None
        self._value: Any = None
        self._invalid_value: Any = None
        self._invalid_since: datetime | None = None
        self._reject_logged: bool = False
        self._last_valid: float | None = None
        self._last_valid_at: datetime | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def async_added_to_hass(self) -> None:
        """Restore the last known good value and process the current data."""
        await super().async_added_to_hass()

        # Keeps cumulative counters continuous across restarts, so an implausible
        # first reading after a restart does not create a gap in the statistics.
        if self._is_numeric and (
            last_data := await self.async_get_last_sensor_data()
        ) is not None:
            if (number := _to_number(last_data.native_value)) is not None:
                self._last_valid = number
                self._last_valid_at = utcnow()

        self._process()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle new data from the coordinator."""
        self._process()
        super()._handle_coordinator_update()

    # ------------------------------------------------------------------
    # Entity properties
    # ------------------------------------------------------------------
    @property
    def device_info(self) -> dict[str, Any]:
        """Return the device this entity belongs to."""
        return {"identifiers": self._device_info["identifiers"]}

    @property
    def available(self) -> bool:
        """Return True if the sensor has a usable value."""
        return super().available and self._value is not None

    @property
    def native_value(self) -> Any:
        """Return the value of the sensor."""
        return self._value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional information about the raw device value."""
        attributes: dict[str, Any] = {}

        if self._raw_value is not None:
            attributes["raw_value"] = self._raw_value

        if self._invalid_value is not None:
            attributes["invalid_value"] = self._invalid_value
            attributes["invalid_since"] = (
                self._invalid_since.isoformat() if self._invalid_since else None
            )

        if self._last_valid_at is not None:
            attributes["last_valid_at"] = self._last_valid_at.isoformat()

        for name, endpoint in self._attributes.items():
            if (value := (self.coordinator.data or {}).get(endpoint)) is not None:
                attributes[name] = value

        return attributes or None

    # ------------------------------------------------------------------
    # Value handling
    # ------------------------------------------------------------------
    @callback
    def _process(self) -> None:
        """Read, convert and validate the current device value."""
        raw_value = (self.coordinator.data or {}).get(self._endpoint)
        self._raw_value = raw_value
        self._value = None
        self._invalid_value = None

        if raw_value is None:
            return

        value: Any = str(raw_value)

        if "ERROR" in value.upper():
            self._reject(value)
            return

        if self._format_dict:
            for old, new in self._format_dict.items():
                value = value.replace(old, new)

        if self._code_dict:
            value = self._code_dict.get(value.upper(), value)

        if self._scale is not None:
            if (number := _to_number(value)) is not None:
                value = round(number * self._scale, 2)

        if not self._is_numeric:
            self._value = value
            return

        number = _to_number(value)
        if number is None:
            self._reject(value)
            return

        if self._min_value is not None and number < self._min_value:
            self._reject(number)
            return

        self._last_valid = number
        self._last_valid_at = utcnow()
        self._invalid_since = None
        self._reject_logged = False
        # Whole numbers are reported as ints, so states render as "268289"
        # instead of "268289.0".
        self._value = int(number) if float(number).is_integer() else number

    @callback
    def _reject(self, value: Any) -> None:
        """Handle a value that is not usable.

        Cumulative meters can never count backwards and a device may report
        bogus values while it starts up, so the value is ignored until the
        device reports something plausible again.
        """
        self._invalid_value = value
        if self._invalid_since is None:
            self._invalid_since = utcnow()

        if not self._ignore_invalid:
            if not self._reject_logged:
                self._reject_logged = True
                LOGGER.warning(
                    "%s: accepting implausible value %s because 'ignore invalid"
                    " values' is disabled",
                    self._key,
                    value,
                )
            self._value = value
            return

        if not self._reject_logged:
            self._reject_logged = True
            LOGGER.warning(
                "%s: ignoring implausible value %s from %s",
                self._key,
                value,
                self._endpoint,
            )

        if self._last_valid is None:
            return

        if self.coordinator.is_stale(self._stale_tolerance):
            LOGGER.debug(
                "%s: no valid value for more than %s minutes, marking unavailable",
                self._key,
                self._stale_tolerance,
            )
            return

        self._value = (
            int(self._last_valid)
            if float(self._last_valid).is_integer()
            else self._last_valid
        )
