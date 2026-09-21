"""Service registration and dispatching for the Pontos integration."""

from __future__ import annotations

import asyncio
import logging
import string
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import CONF_HTTP_TIMEOUT
from .const import CONF_IP_ADDRESS
from .const import CONF_PORT
from .const import DOMAIN
from .const import MAKES
from .const import get_device_const
from .const import get_option
from .utils import send_command

LOGGER = logging.getLogger(__name__)

ATTR_ENTRY_ID = "entry_id"
ATTR_DEVICE_ID = "device_id"
ATTR_DATA = "data"


PROFILE_RANGE = vol.All(vol.Coerce(int), vol.Range(min=1, max=8))


def _schema(fields: dict[Any, Any] | None = None) -> vol.Schema:
    """Return a service schema including the common target fields."""
    schema: dict[Any, Any] = dict(fields or {})
    schema[vol.Optional(ATTR_ENTRY_ID)] = cv.string
    schema[vol.Optional(ATTR_DEVICE_ID)] = cv.string
    return vol.Schema(schema)


#: Service schemas. Services that are not listed fall back to a schema that only
#: contains the target fields.
SERVICE_SCHEMAS: dict[str, vol.Schema] = {
    "open_valve": _schema(),
    "close_valve": _schema(),
    "clear_alarms": _schema(),
    "clear_warnings": _schema(),
    "clear_notifications": _schema(),
    "enable_buzzer": _schema(),
    "disable_buzzer": _schema(),
    "microleakage_test": _schema(),
    "start_self_study": _schema(
        {
            vol.Required("days"): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=28)
            )
        }
    ),
    "delete_self_study": _schema(),
    "set_profile": _schema({vol.Required("profile"): PROFILE_RANGE}),
    "set_profile_volume": _schema(
        {
            vol.Required("profile"): PROFILE_RANGE,
            vol.Required("volume"): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=9000)
            ),
        }
    ),
    "set_profile_time": _schema(
        {
            vol.Required("profile"): PROFILE_RANGE,
            vol.Required("minutes"): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=1500)
            ),
        }
    ),
    "set_profile_flow": _schema(
        {
            vol.Required("profile"): PROFILE_RANGE,
            vol.Required("flow"): vol.All(vol.Coerce(int), vol.Range(min=0, max=5000)),
        }
    ),
    "set_profile_return_time": _schema(
        {
            vol.Required("profile"): PROFILE_RANGE,
            vol.Required("hours"): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=700)
            ),
        }
    ),
    "set_profile_availability": _schema(
        {
            vol.Required("profile"): PROFILE_RANGE,
            vol.Required("enabled"): cv.boolean,
        }
    ),
    "set_profile_warning": _schema(
        {
            vol.Required("profile"): PROFILE_RANGE,
            vol.Required("enabled"): cv.boolean,
        }
    ),
    "microleakage_schedule": _schema(
        {
            vol.Required("schedule"): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=3)
            )
        }
    ),
    "microleakage_time": _schema({vol.Required("time"): cv.string}),
    "set_regeneration_mode": _schema(
        {vol.Required("mode"): vol.All(vol.Coerce(int), vol.Range(min=1, max=4))}
    ),
    "set_regeneration_interval": _schema(
        {vol.Required("days"): vol.All(vol.Coerce(int), vol.Range(min=1, max=3))}
    ),
    "set_regeneration_time": _schema({vol.Required("time"): cv.string}),
    "generic_service": _schema(
        {
            vol.Required("endpoint"): cv.string,
            vol.Required(ATTR_DATA): cv.string,
        }
    ),
}


def _placeholders(endpoint: str) -> list[str]:
    """Return the format placeholders of an endpoint template."""
    return [
        field_name
        for _, field_name, _, _ in string.Formatter().parse(endpoint)
        if field_name
    ]


def _all_services() -> dict[str, dict[str, Any]]:
    """Return all services offered by any supported device family."""
    services: dict[str, dict[str, Any]] = {}
    for device_const in MAKES.values():
        for name, config in getattr(device_const, "SERVICES", {}).items():
            services.setdefault(name, config)
    return services


def _targeted_entries(hass: HomeAssistant, call: ServiceCall) -> list[dict[str, Any]]:
    """Return the entries a service call is aimed at."""
    entries: dict[str, dict[str, Any]] = hass.data.get(DOMAIN, {}).get("entries", {})

    if entry_id := call.data.get(ATTR_ENTRY_ID):
        if (entry_data := entries.get(entry_id)) is None:
            raise ServiceValidationError(f"Unknown config entry '{entry_id}'")
        return [entry_data]

    if device_id := call.data.get(ATTR_DEVICE_ID):
        device_entry = dr.async_get(hass).async_get(device_id)
        if device_entry is None:
            raise ServiceValidationError(f"Unknown device '{device_id}'")
        if (entry_id := device_entry.config_entry_id) and (
            entry_data := entries.get(entry_id)
        ):
            return [entry_data]

        raise ServiceValidationError(
            f"Device '{device_id}' does not belong to this integration"
        )

    if len(entries) > 1:
        LOGGER.warning(
            "Service %s was called without a target, sending the command to all"
            " %s configured devices",
            call.service,
            len(entries),
        )

    return list(entries.values())


def _resolve_payload(endpoint: str, call: ServiceCall) -> dict[str, Any]:
    """Map the service data onto the placeholders of the endpoint template."""
    placeholders = _placeholders(endpoint)
    if not placeholders:
        return {}

    payload: dict[str, Any] = {}
    for name in placeholders:
        if name in call.data:
            payload[name] = call.data[name]
        elif ATTR_DATA in call.data and len(placeholders) == 1:
            # Backwards compatibility with the old `data` service field.
            payload[name] = call.data[ATTR_DATA]
        else:
            raise ServiceValidationError(
                f"Service call is missing the required field '{name}'"
            )

    return payload


async def async_send_command(
    hass: HomeAssistant,
    entry_id: str,
    entry_data: dict[str, Any],
    endpoint: str,
    payload: dict[str, Any],
) -> bool:
    """Send a command to a single device."""
    entry = entry_data["entry"]
    coordinator = entry_data["coordinator"]
    device_const = get_device_const(entry)

    return await send_command(
        hass,
        get_option(entry, CONF_IP_ADDRESS),
        device_const.BASE_URL,
        endpoint,
        payload,
        port=get_option(entry, CONF_PORT),
        timeout=get_option(entry, CONF_HTTP_TIMEOUT),
    )


async def async_service_handler(
    hass: HomeAssistant, call: ServiceCall, service_name: str
) -> None:
    """Handle a service call for one or more devices."""
    entries = _targeted_entries(hass, call)

    unsupported: list[str] = []
    for entry_data in entries:
        entry = entry_data["entry"]
        device_const = get_device_const(entry)
        config = getattr(device_const, "SERVICES", {}).get(service_name)

        if config is None:
            unsupported.append(entry.title)
            continue

        endpoint = config["endpoint"]
        payload = _resolve_payload(endpoint, call)

        lock: asyncio.Lock = entry_data["command_lock"]
        if lock.locked():
            LOGGER.warning(
                "Service '%s' skipped for %s: previous command still running",
                service_name,
                entry.title,
            )
            continue

        async with lock:
            try:
                await async_send_command(
                    hass, entry.entry_id, entry_data, endpoint, payload
                )
            except HomeAssistantError:
                raise
            except Exception as err:  # noqa: BLE001 - reported to the caller
                raise HomeAssistantError(
                    f"Command '{service_name}' failed for {entry.title}: {err}"
                ) from err

            await entry_data["coordinator"].async_refresh()

    if unsupported and len(unsupported) == len(entries):
        raise ServiceValidationError(
            f"Service '{service_name}' is not supported by {', '.join(unsupported)}"
        )


async def async_register_services(hass: HomeAssistant) -> None:
    """Register all services offered by the supported devices."""
    hass.data.setdefault(DOMAIN, {}).setdefault("services", {})
    registered: set[str] = hass.data[DOMAIN]["services"]

    for service_name in _all_services():
        if service_name in registered:
            continue

        async def service_handler(call: ServiceCall, _name: str = service_name) -> None:
            await async_service_handler(hass, call, _name)

        schema = SERVICE_SCHEMAS.get(service_name, _schema())

        hass.services.async_register(
            DOMAIN, service_name, service_handler, schema=schema
        )
        registered.add(service_name)


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove all services of this integration."""
    for service_name in list(hass.data.get(DOMAIN, {}).get("services", set())):
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)

    hass.data.get(DOMAIN, {}).pop("services", None)
