"""Device registry handling for Pontos / SYR devices."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

from .const import CONF_IP_ADDRESS
from .const import CONF_PORT
from .const import DOMAIN
from .const import get_device_const
from .const import get_device_name
from .const import get_option

LOGGER = logging.getLogger(__name__)

MAC_PATTERN = re.compile(r"^([0-9a-f]{2}[:-]){5}[0-9a-f]{2}$", re.IGNORECASE)

#: Upper limit of profile entities, the devices report 1-8 profiles.
MAX_PROFILES = 8


def profile_limit(device_const, coordinator) -> int:
    """Return how many profiles the device reports."""
    endpoint = getattr(device_const, "PROFILE_COUNT_ENDPOINT", None)
    if not endpoint:
        return MAX_PROFILES

    raw_value = (coordinator.data or {}).get(endpoint)
    try:
        return max(0, min(MAX_PROFILES, int(str(raw_value))))
    except (TypeError, ValueError):
        return MAX_PROFILES


def _endpoint_value(data: dict[str, Any], device_const, key: str) -> str | None:
    """Return the raw value of a device endpoint."""
    endpoint = getattr(device_const, "SENSOR_DETAILS", {}).get(key, {}).get("endpoint")
    if not endpoint:
        return None

    value = data.get(endpoint)
    if value is None:
        return None

    return str(value).strip()


def _clean_mac(value: str | None) -> str | None:
    """Return a normalised MAC address, or None if it is not usable."""
    if not value:
        return None

    if MAC_PATTERN.match(value):
        return value.upper()

    return None


async def get_device_info(
    entry: ConfigEntry, coordinator
) -> DeviceInfo:
    """Build the DeviceInfo of a device from its first data sample."""
    device_const = get_device_const(entry)

    data = coordinator.data
    if not data:
        raise ValueError("No data available from the coordinator")

    mac_address = _clean_mac(_endpoint_value(data, device_const, "mac_address"))
    serial_number = _endpoint_value(data, device_const, "serial_number")
    firmware_version = _endpoint_value(data, device_const, "firmware_version")
    hardware_version = _endpoint_value(data, device_const, "hardware_version")

    if mac_address is None and not serial_number:
        LOGGER.warning(
            "Device %s did not report a serial number or MAC address, falling back"
            " to the config entry id as identifier",
            entry.title,
        )

    identifiers: set[tuple[str, str]] = set()
    if serial_number:
        identifiers.add((DOMAIN, serial_number))
    elif mac_address:
        identifiers.add((DOMAIN, mac_address))
    else:
        identifiers.add((DOMAIN, entry.entry_id))

    device_info = DeviceInfo(
        identifiers=identifiers,
        name=get_device_name(entry),
        manufacturer=device_const.MANUFACTURER,
        model=device_const.MODEL,
        configuration_url=(
            f"http://{get_option(entry, CONF_IP_ADDRESS)}:"
            f"{get_option(entry, CONF_PORT)}"
        ),
    )

    if mac_address:
        device_info["connections"] = {(CONNECTION_NETWORK_MAC, mac_address)}

    if serial_number:
        device_info["serial_number"] = serial_number

    if firmware_version:
        device_info["sw_version"] = firmware_version

    if hardware_version:
        device_info["hw_version"] = hardware_version

    return device_info


async def register_device(
    hass: HomeAssistant, entry: ConfigEntry, coordinator=None
) -> DeviceInfo:
    """Register (or update) the device of a config entry."""
    device_info = await get_device_info(entry, coordinator)

    hass.data[DOMAIN]["entries"][entry.entry_id]["device_info"] = device_info

    device_registry = async_get_device_registry(hass)
    device_registry.async_get_or_create(config_entry_id=entry.entry_id, **device_info)

    return device_info


def get_stored_device_info(hass: HomeAssistant, entry_id: str) -> DeviceInfo | None:
    """Return the DeviceInfo that was stored during setup."""
    entry_data = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry_id)
    if entry_data is None:
        return None
    return entry_data["device_info"]


def device_identifier(device_info: DeviceInfo | None, entry: ConfigEntry) -> str:
    """Return a stable per device identifier used to build entity unique ids."""
    if device_info:
        if serial_number := device_info.get("serial_number"):
            return str(serial_number)

        for _domain, identifier in sorted(device_info.get("identifiers") or ()):
            return str(identifier)

    return entry.entry_id
