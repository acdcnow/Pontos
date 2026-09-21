"""Config and options flow for the Pontos / SYR integration."""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.config_entries import OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import BooleanSelector
from homeassistant.helpers.selector import NumberSelector
from homeassistant.helpers.selector import NumberSelectorConfig
from homeassistant.helpers.selector import NumberSelectorMode
from homeassistant.helpers.selector import SelectSelector
from homeassistant.helpers.selector import SelectSelectorConfig
from homeassistant.helpers.selector import TextSelector

from .const import CONF_DEBUG_LOGGING
from .const import CONF_DEVICE_NAME
from .const import CONF_ENABLE_CONTROLS
from .const import CONF_ENABLE_DIAGNOSTICS
from .const import CONF_FETCH_INTERVAL
from .const import CONF_HTTP_TIMEOUT
from .const import CONF_IGNORE_INVALID_VALUES
from .const import CONF_IP_ADDRESS
from .const import CONF_MAKE
from .const import CONF_PORT
from .const import CONF_RETRY_ATTEMPTS
from .const import CONF_RETRY_DELAY
from .const import CONF_STALE_TOLERANCE
from .const import CONF_VOLUME_UNIT
from .const import DEFAULT_FETCH_INTERVAL
from .const import DEFAULT_HTTP_TIMEOUT
from .const import DEFAULT_MAKE
from .const import DEFAULT_PORT
from .const import DOMAIN
from .const import LEGACY_DOMAIN
from .const import MAKES
from .const import MAX_FETCH_INTERVAL
from .const import MAX_HTTP_TIMEOUT
from .const import MAX_RETRY_ATTEMPTS
from .const import MAX_RETRY_DELAY
from .const import MAX_STALE_TOLERANCE
from .const import MIN_FETCH_INTERVAL
from .const import MIN_HTTP_TIMEOUT
from .const import MIN_RETRY_ATTEMPTS
from .const import MIN_RETRY_DELAY
from .const import VOLUME_UNITS
from .const import get_option
from .const import normalise_options
from .utils import fetch_data

LOGGER = logging.getLogger(__name__)

IP_SCHEMA = TextSelector()
PORT_SCHEMA = NumberSelector(
    NumberSelectorConfig(min=1, max=65535, step=1, mode=NumberSelectorMode.BOX)
)

#: Host names (mDNS, DNS, NetBIOS) are accepted as well as IP addresses, so
#: "pontos.fritz.box" works like "192.168.1.100".
HOST_PATTERN = re.compile(
    r"^(?=.{1,253}$)"
    r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)


def _valid_host(value: str | None) -> bool:
    """Return True for an IPv4/IPv6 address or a host name."""
    host = (value or "").strip()
    if not host:
        return False

    try:
        ipaddress.ip_address(host)
    except ValueError:
        return bool(HOST_PATTERN.match(host))

    return True


def _clean_host(value: Any) -> str:
    """Return the entered host without surrounding whitespace."""
    return str(value or "").strip()


async def async_connection_works(
    hass: HomeAssistant,
    ip_address: str,
    port: int,
    make: str,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
) -> bool:
    """Test whether the device answers on all of its endpoints."""
    if (device_const := MAKES.get(make)) is None:
        return False

    data = await fetch_data(
        hass,
        ip_address,
        device_const.URL_LIST,
        port=port,
        timeout=timeout,
        max_attempts=1,
    )

    if not data:
        return False

    LOGGER.debug(
        "%s answered with %s value(s): %s",
        ip_address,
        len(data),
        ", ".join(sorted(data)[:10]),
    )
    return True


def _interval_schema() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=MIN_FETCH_INTERVAL,
            max=MAX_FETCH_INTERVAL,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="s",
        )
    )


def _timeout_schema() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=MIN_HTTP_TIMEOUT,
            max=MAX_HTTP_TIMEOUT,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="s",
        )
    )


def _attempts_schema() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=MIN_RETRY_ATTEMPTS,
            max=MAX_RETRY_ATTEMPTS,
            step=1,
            mode=NumberSelectorMode.BOX,
        )
    )


def _retry_delay_schema() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=MIN_RETRY_DELAY,
            max=MAX_RETRY_DELAY,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="s",
        )
    )


def _stale_schema() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=0,
            max=MAX_STALE_TOLERANCE,
            step=5,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="min",
        )
    )


def _make_schema() -> SelectSelector:
    return SelectSelector(SelectSelectorConfig(options=list(MAKES)))


def _volume_unit_schema() -> SelectSelector:
    return SelectSelector(SelectSelectorConfig(options=list(VOLUME_UNITS)))


class PontosConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup of a Pontos / SYR device."""

    VERSION = 5

    def __init__(self) -> None:
        """Initialise the flow."""
        self._legacy_entry: ConfigEntry | None = None

    async def async_step_user(self, user_input=None):
        """Ask for the connection details of a new device."""
        if (
            legacy_entries := self.hass.config_entries.async_entries(LEGACY_DOMAIN)
        ) and user_input is None:
            # A configuration from a release before 2.9.3 was found, offer to
            # take it over instead of asking the user to enter everything again.
            self._legacy_entry = legacy_entries[0]
            return await self.async_step_adopt_legacy()

        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._async_validate(user_input)
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_DEVICE_NAME],
                    data={
                        CONF_DEVICE_NAME: user_input[CONF_DEVICE_NAME],
                        CONF_MAKE: user_input[CONF_MAKE],
                    },
                    options=normalise_options(
                        {
                            CONF_IP_ADDRESS: _clean_host(user_input[CONF_IP_ADDRESS]),
                            CONF_PORT: user_input[CONF_PORT],
                            CONF_FETCH_INTERVAL: user_input[CONF_FETCH_INTERVAL],
                        }
                    ),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self._user_schema(),
            errors=errors,
        )

    async def async_step_adopt_legacy(self, user_input=None):
        """Take over the configuration of a pre 2.9.3 config entry."""
        legacy = self._legacy_entry
        assert legacy is not None

        defaults = {
            CONF_IP_ADDRESS: get_option(legacy, CONF_IP_ADDRESS),
            CONF_PORT: get_option(legacy, CONF_PORT),
            CONF_FETCH_INTERVAL: get_option(legacy, CONF_FETCH_INTERVAL),
            CONF_DEVICE_NAME: legacy.data.get(CONF_DEVICE_NAME) or legacy.title,
            CONF_MAKE: legacy.data.get(CONF_MAKE, DEFAULT_MAKE),
        }
        errors: dict[str, str] = {}

        if user_input is not None:
            if not (errors := await self._async_validate(user_input)):
                # Removing the old entry also removes its entities from the entity
                # registry, so the new entities can use the same entity ids again.
                LOGGER.info(
                    "Adopting configuration '%s' and removing the old '%s' entry",
                    legacy.title,
                    LEGACY_DOMAIN,
                )
                await self.hass.config_entries.async_remove(legacy.entry_id)

                return self.async_create_entry(
                    title=user_input[CONF_DEVICE_NAME],
                    data={
                        CONF_DEVICE_NAME: user_input[CONF_DEVICE_NAME],
                        CONF_MAKE: user_input[CONF_MAKE],
                    },
                    options=normalise_options(
                        {
                            CONF_IP_ADDRESS: _clean_host(user_input[CONF_IP_ADDRESS]),
                            CONF_PORT: user_input[CONF_PORT],
                            CONF_FETCH_INTERVAL: user_input[CONF_FETCH_INTERVAL],
                        }
                    ),
                )

        return self.async_show_form(
            step_id="adopt_legacy",
            data_schema=self.add_suggested_values_to_schema(
                self._user_schema(), defaults
            ),
            errors=errors,
            description_placeholders={"title": legacy.title},
        )

    def _user_schema(self) -> vol.Schema:
        """Return the schema used to add or adopt a device."""
        return vol.Schema(
            {
                vol.Required(CONF_IP_ADDRESS, default="192.168.1.100"): IP_SCHEMA,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): PORT_SCHEMA,
                vol.Required(
                    CONF_FETCH_INTERVAL, default=DEFAULT_FETCH_INTERVAL
                ): _interval_schema(),
                vol.Required(CONF_DEVICE_NAME, default="Pontos"): TextSelector(),
                vol.Required(CONF_MAKE, default=DEFAULT_MAKE): _make_schema(),
            }
        )

    async def _async_validate(self, user_input: dict) -> dict[str, str]:
        """Validate the given connection details."""
        if not _valid_host(user_input[CONF_IP_ADDRESS]):
            return {"base": "invalid_ip"}

        if not await async_connection_works(
            self.hass,
            _clean_host(user_input[CONF_IP_ADDRESS]),
            user_input[CONF_PORT],
            user_input[CONF_MAKE],
        ):
            return {"base": "cannot_connect"}

        return {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return PontosOptionsFlow()


class PontosOptionsFlow(OptionsFlow):
    """Allow the user to change the settings of an existing device."""

    async def async_step_init(self, user_input=None):
        """Show the settings form."""
        entry = self.config_entry
        errors: dict[str, str] = {}
        suggested = self._section_values(self._current_options())

        if user_input is not None:
            options = self._flatten(user_input)
            # If the form has to be shown again, keep what the user entered.
            suggested = self._section_values(options)
            ip_address = options[CONF_IP_ADDRESS]

            if not _valid_host(ip_address):
                errors["base"] = "invalid_ip"

            if not errors and ip_address != get_option(entry, CONF_IP_ADDRESS):
                if not await async_connection_works(
                    self.hass,
                    ip_address,
                    options[CONF_PORT],
                    options[CONF_MAKE],
                    options[CONF_HTTP_TIMEOUT],
                ):
                    errors["base"] = "cannot_connect"

            if not errors:
                # The device name is also the title of the config entry.
                new_name = options[CONF_DEVICE_NAME]
                self.hass.config_entries.async_update_entry(entry, title=new_name)

                return self.async_create_entry(data=options)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                self._options_schema(), suggested
            ),
            errors=errors,
        )

    def _current_options(self) -> dict:
        """Return the current settings, including the entry title."""
        entry = self.config_entry
        values = {
            key: get_option(entry, key)
            for key in (
                CONF_IP_ADDRESS,
                CONF_PORT,
                CONF_FETCH_INTERVAL,
                CONF_HTTP_TIMEOUT,
                CONF_RETRY_ATTEMPTS,
                CONF_RETRY_DELAY,
                CONF_IGNORE_INVALID_VALUES,
                CONF_STALE_TOLERANCE,
                CONF_VOLUME_UNIT,
                CONF_ENABLE_DIAGNOSTICS,
                CONF_ENABLE_CONTROLS,
                CONF_DEBUG_LOGGING,
            )
        }
        values[CONF_DEVICE_NAME] = entry.title
        values[CONF_MAKE] = get_option(entry, CONF_MAKE) or entry.data.get(
            CONF_MAKE, DEFAULT_MAKE
        )
        return values

    #: Section of the settings form -> the options it contains. Order matters
    #: for the generated form only, the values are stored flat.
    SECTION_OPTIONS: dict[str, tuple[str, ...]] = {
        "connection": (
            CONF_IP_ADDRESS,
            CONF_PORT,
            CONF_HTTP_TIMEOUT,
            CONF_RETRY_ATTEMPTS,
            CONF_RETRY_DELAY,
        ),
        "polling": (CONF_FETCH_INTERVAL,),
        "device": (CONF_DEVICE_NAME, CONF_MAKE),
        "data_quality": (
            CONF_IGNORE_INVALID_VALUES,
            CONF_STALE_TOLERANCE,
            CONF_VOLUME_UNIT,
        ),
        "entities": (CONF_ENABLE_DIAGNOSTICS, CONF_ENABLE_CONTROLS),
        "logging": (CONF_DEBUG_LOGGING,),
    }

    @classmethod
    def _section_values(cls, options: dict) -> dict[str, dict]:
        """Group flat option values into the sections of the form.

        `add_suggested_values_to_schema` only fills the fields of a `section`
        when the suggested values are nested under the section name, so a flat
        mapping would leave the form empty.
        """
        return {
            section: {key: options[key] for key in keys if key in options}
            for section, keys in cls.SECTION_OPTIONS.items()
        }

    def _options_schema(self) -> vol.Schema:
        """Return the grouped settings schema."""
        return vol.Schema(
            {
                vol.Required("connection"): section(
                    vol.Schema(
                        {
                            vol.Required(CONF_IP_ADDRESS): IP_SCHEMA,
                            vol.Required(CONF_PORT): PORT_SCHEMA,
                            vol.Required(CONF_HTTP_TIMEOUT): _timeout_schema(),
                            vol.Required(CONF_RETRY_ATTEMPTS): _attempts_schema(),
                            vol.Required(CONF_RETRY_DELAY): _retry_delay_schema(),
                        }
                    ),
                    {"collapsed": False},
                ),
                vol.Required("polling"): section(
                    vol.Schema(
                        {
                            vol.Required(CONF_FETCH_INTERVAL): _interval_schema(),
                        }
                    ),
                    {"collapsed": True},
                ),
                vol.Required("device"): section(
                    vol.Schema(
                        {
                            vol.Required(CONF_DEVICE_NAME): TextSelector(),
                            vol.Required(CONF_MAKE): _make_schema(),
                        }
                    ),
                    {"collapsed": True},
                ),
                vol.Required("data_quality"): section(
                    vol.Schema(
                        {
                            vol.Required(CONF_IGNORE_INVALID_VALUES): BooleanSelector(),
                            vol.Required(CONF_STALE_TOLERANCE): _stale_schema(),
                            vol.Required(CONF_VOLUME_UNIT): _volume_unit_schema(),
                        }
                    ),
                    {"collapsed": True},
                ),
                vol.Required("entities"): section(
                    vol.Schema(
                        {
                            vol.Required(CONF_ENABLE_DIAGNOSTICS): BooleanSelector(),
                            vol.Required(CONF_ENABLE_CONTROLS): BooleanSelector(),
                        }
                    ),
                    {"collapsed": True},
                ),
                vol.Required("logging"): section(
                    vol.Schema(
                        {
                            vol.Required(CONF_DEBUG_LOGGING): BooleanSelector(),
                        }
                    ),
                    {"collapsed": True},
                ),
            }
        )

    @staticmethod
    def _flatten(user_input: dict) -> dict:
        """Flatten the sectioned form input and fix the value types."""
        options: dict = {}
        for value in user_input.values():
            if isinstance(value, dict):
                options.update(value)

        options = normalise_options(options)
        if (host := options.get(CONF_IP_ADDRESS)) is not None:
            options[CONF_IP_ADDRESS] = _clean_host(host)
        return options
