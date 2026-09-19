from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.util import slugify
import logging

from .const import CONF_MAKE, MAKES, DOMAIN

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    make = entry.data.get(CONF_MAKE)
    device_const = MAKES[make]
    SENSOR_DETAILS = device_const.SENSOR_DETAILS
    coordinator = hass.data[DOMAIN]["entries"][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN]["entries"][entry.entry_id]["device_info"]

    sensors = [
        PontosSensor(key, sensor_config, device_info, coordinator)
        for key, sensor_config in SENSOR_DETAILS.items()
    ]
    async_add_entities(sensors)


class PontosSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, key, sensor_config, device_info, coordinator):
        super().__init__(coordinator)
        self._key = key
        self._endpoint = sensor_config["endpoint"]
        self._attr_translation_key = key
        self._attr_has_entity_name = True
        self._attr_native_unit_of_measurement = sensor_config.get("unit", None)
        self._attr_device_class = sensor_config.get("device_class", None)
        self._attr_entity_category = sensor_config.get("entity_category", None)
        self._attr_state_class = sensor_config.get("state_class", None)
        self._format_dict = sensor_config.get("format_dict", None)
        self._code_dict = sensor_config.get("code_dict", None)
        self._scale = sensor_config.get("scale", None)
        self._attributes = sensor_config.get("attributes", {})
        # A sensor that declares a state_class is recorded by Home Assistant and must
        # therefore report a real number, never a string. Cumulative
        # ("total_increasing") meters can additionally never count backwards, so they
        # are clamped at zero. Both can be overridden per sensor in the device config.
        state_class = getattr(self._attr_state_class, "value", self._attr_state_class)
        self._is_total_meter = state_class == "total_increasing"
        self._numeric = sensor_config.get("numeric", state_class is not None)
        self._clamp_min = sensor_config.get(
            "clamp_min", 0 if self._is_total_meter else None
        )
        self._attr_unique_id = slugify(
            f"{device_info['serial_number']}_{sensor_config['name']}"
        )
        self._device_info = device_info

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def device_info(self):
        return {
            "identifiers": self._device_info["identifiers"],
        }

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return self.parse_data(data)

    @property
    def available(self):
        data = self.coordinator.data or {}
        return self.parse_data(data) is not None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        attributes = {}

        # Always add the raw value of the main sensor endpoint
        raw_value = data.get(self._endpoint)
        if raw_value is not None:
            attributes["raw_value"] = raw_value

        # Add explicitly defined attributes
        if self._attributes:
            attributes.update(
                {
                    attr_name: data.get(endpoint)
                    for attr_name, endpoint in self._attributes.items()
                    if data.get(endpoint) is not None
                }
            )

        return attributes if attributes else None

    # Parsing and updating sensor data
    def parse_data(self, data):
        """Process, format, and validate sensor data."""
        _data = data.get(self._endpoint, None)

        # If data is None, set to None and return
        if _data is None:
            return None

        # Convert to string for more consistent manipulation later
        _data = str(_data)

        # If the device returns some known error string (e.g., "ERROR: ADM"), mark sensor unavailable
        if "ERROR" in _data.upper():
            return None

        # Apply format replacements if format_dict is present
        if self._format_dict is not None and _data is not None:
            for old, new in self._format_dict.items():
                _data = _data.replace(old, new)

        # Translate alarm codes if code_dict is present
        if self._code_dict is not None and _data is not None:
            _data = self._code_dict.get(_data.upper(), _data)

        # Scale sensor data if scale is present
        if self._scale is not None and _data is not None:
            try:
                _data = round(float(_data) * self._scale, 2)
            except (ValueError, TypeError):
                pass

        # Numeric sensors have to hand Home Assistant a real number. Returning a
        # string for a sensor that declares a state_class breaks the water/energy
        # statistics and shows up as a wrong or missing reading on the dashboard.
        if self._numeric and _data is not None:
            try:
                number = float(_data)
            except (ValueError, TypeError):
                LOGGER.warning(
                    "%s: expected a number for '%s' but got '%s' - marking unavailable",
                    self._key,
                    self._endpoint,
                    _data,
                )
                return None

            # A cumulative meter can only grow, so a negative reading is invalid and
            # would otherwise poison the long-term statistics. Clamp it instead.
            if self._clamp_min is not None and number < self._clamp_min:
                LOGGER.warning(
                    "%s: '%s' reported an invalid value of %s, clamping to %s",
                    self._key,
                    self._endpoint,
                    number,
                    self._clamp_min,
                )
                number = self._clamp_min

            # Keep whole numbers as ints so states render as "268289", not "268289.0".
            _data = int(number) if float(number).is_integer() else number

        # Update sensor data
        return _data
