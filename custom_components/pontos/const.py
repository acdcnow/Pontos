"""Constants and option helpers for the Pontos integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from .device_config import conf_neosoft
from .device_config import conf_pontos
from .device_config import conf_safetech
from .device_config import conf_safetech_v4
from .device_config import conf_trio

DOMAIN = "pontos"

# Domain used by releases before 2.9.3. Existing config entries using it are
# adopted by the config flow so users do not have to reconfigure their device.
LEGACY_DOMAIN = "hass_pontos"

# ---------------------------------------------------------------------------
# Config entry keys
# ---------------------------------------------------------------------------
CONF_MAKE = "make"
CONF_DEVICE_NAME = "device_name"

# Connection
CONF_IP_ADDRESS = "ip_address"
CONF_PORT = "port"
CONF_HTTP_TIMEOUT = "http_timeout"
CONF_RETRY_ATTEMPTS = "retry_attempts"
CONF_RETRY_DELAY = "retry_delay"

# Polling
CONF_FETCH_INTERVAL = "fetch_interval"

# Data quality
CONF_IGNORE_INVALID_VALUES = "ignore_invalid_values"
CONF_STALE_TOLERANCE = "stale_tolerance"
CONF_VOLUME_UNIT = "volume_unit"

# Entities
CONF_ENABLE_DIAGNOSTICS = "enable_diagnostics"
CONF_ENABLE_CONTROLS = "enable_controls"

# Logging
CONF_DEBUG_LOGGING = "debug_logging"

# ---------------------------------------------------------------------------
# Defaults and limits
# ---------------------------------------------------------------------------
DEFAULT_PORT = 5333
DEFAULT_FETCH_INTERVAL = 10
DEFAULT_HTTP_TIMEOUT = 5
DEFAULT_RETRY_ATTEMPTS = 2
DEFAULT_RETRY_DELAY = 2

MIN_FETCH_INTERVAL = 5
MAX_FETCH_INTERVAL = 3600
MIN_HTTP_TIMEOUT = 1
MAX_HTTP_TIMEOUT = 60
MIN_RETRY_ATTEMPTS = 1
MAX_RETRY_ATTEMPTS = 10
MIN_RETRY_DELAY = 1
MAX_RETRY_DELAY = 60

# Minutes a previously valid value may be kept while the device keeps sending
# implausible values. 0 disables the tolerance (the last valid value is kept
# until a valid value arrives again).
DEFAULT_STALE_TOLERANCE = 60
MAX_STALE_TOLERANCE = 1440

#: Selectable display units for volumetric sensors.
VOLUME_UNITS: dict[str, str] = {"L": "L", "m³": "m³"}
DEFAULT_VOLUME_UNIT = "L"

#: All options with their defaults, used to normalise old config entries.
OPTION_DEFAULTS: dict[str, Any] = {
    CONF_IP_ADDRESS: None,
    CONF_PORT: DEFAULT_PORT,
    CONF_HTTP_TIMEOUT: DEFAULT_HTTP_TIMEOUT,
    CONF_RETRY_ATTEMPTS: DEFAULT_RETRY_ATTEMPTS,
    CONF_RETRY_DELAY: DEFAULT_RETRY_DELAY,
    CONF_FETCH_INTERVAL: DEFAULT_FETCH_INTERVAL,
    CONF_IGNORE_INVALID_VALUES: True,
    CONF_STALE_TOLERANCE: DEFAULT_STALE_TOLERANCE,
    CONF_VOLUME_UNIT: DEFAULT_VOLUME_UNIT,
    CONF_ENABLE_DIAGNOSTICS: True,
    CONF_ENABLE_CONTROLS: True,
    CONF_DEBUG_LOGGING: False,
}

#: Options that must be integral. The frontend number selector always returns a
#: float, which would end up in the device URL ("http://host:5333.0/...") and in
#: range()/list indexing at runtime.
INT_OPTIONS: frozenset[str] = frozenset(
    {
        CONF_PORT,
        CONF_HTTP_TIMEOUT,
        CONF_RETRY_ATTEMPTS,
        CONF_RETRY_DELAY,
        CONF_FETCH_INTERVAL,
        CONF_STALE_TOLERANCE,
    }
)

MAKES = {
    "Hansgrohe Pontos": conf_pontos,
    "SYR Trio": conf_trio,
    "SYR SafeTech+": conf_safetech,
    "SYR SafeTech+ (Old firmware)": conf_safetech_v4,
    "SYR NeoSoft": conf_neosoft,
}

DEFAULT_MAKE = "Hansgrohe Pontos"


def get_make(entry: ConfigEntry) -> str:
    """Return the device family of a config entry.

    The model can be changed from the options flow, therefore options win over
    the data that was stored when the entry was created.
    """
    make = entry.options.get(CONF_MAKE) or entry.data.get(CONF_MAKE) or DEFAULT_MAKE
    if make not in MAKES:
        return DEFAULT_MAKE
    return make


def get_device_const(entry: ConfigEntry):
    """Return the device configuration module of a config entry."""
    return MAKES[get_make(entry)]


def coerce_option(key: str, value: Any) -> Any:
    """Return an option value coerced to the type it is used as."""
    if value is None or key not in INT_OPTIONS:
        return value

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return OPTION_DEFAULTS.get(key)


def get_option(entry: ConfigEntry, key: str) -> Any:
    """Return an option, falling back to its default.

    Values are coerced on read, so entries that stored a float port (the
    frontend number selector always returns a float) work again as well.
    """
    if (value := entry.options.get(key)) is not None:
        return coerce_option(key, value)
    if (value := entry.data.get(key)) is not None:
        return coerce_option(key, value)
    return OPTION_DEFAULTS.get(key)


def get_device_name(entry: ConfigEntry) -> str:
    """Return the user defined device name."""
    return (
        entry.options.get(CONF_DEVICE_NAME)
        or entry.data.get(CONF_DEVICE_NAME)
        or entry.title
    )


def normalise_options(options: dict[str, Any]) -> dict[str, Any]:
    """Fill in missing options with their defaults and fix their types."""
    normalised = dict(options)
    for key, default in OPTION_DEFAULTS.items():
        if normalised.get(key) is None:
            if default is not None:
                normalised[key] = default
            continue
        normalised[key] = coerce_option(key, normalised[key])
    return normalised
