"""Shared builders for the per device configuration modules."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

PROBLEM = BinarySensorDeviceClass.PROBLEM


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
def build_profile_services(
    *, availability: bool = True, warning: bool = True
) -> dict[str, dict[str, Any]]:
    """Return the services that change profile settings."""
    services: dict[str, dict[str, Any]] = {
        "set_profile_volume": {
            "name": "Set profile volume",
            "endpoint": "set/pv{profile}/{volume}",
        },
        "set_profile_time": {
            "name": "Set profile time",
            "endpoint": "set/pt{profile}/{minutes}",
        },
        "set_profile_flow": {
            "name": "Set profile flow",
            "endpoint": "set/pf{profile}/{flow}",
        },
        "set_profile_return_time": {
            "name": "Set profile return time",
            "endpoint": "set/pr{profile}/{hours}",
        },
    }

    if availability:
        services["set_profile_availability"] = {
            "name": "Set profile availability",
            "endpoint": "set/pa{profile}/{enabled}",
        }

    if warning:
        services["set_profile_warning"] = {
            "name": "Set profile leakage warning",
            "endpoint": "set/pw{profile}/{enabled}",
        }

    return services


def build_self_study_services() -> dict[str, dict[str, Any]]:
    """Return the services of the self-study phase."""
    return {
        "start_self_study": {
            "name": "Start self-study",
            "endpoint": "set/slp/{days}",
        },
        "delete_self_study": {
            "name": "Delete self-study values",
            "endpoint": "set/sld/true",
        },
    }


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------
def build_self_study_sensors() -> dict[str, dict[str, Any]]:
    """Return the sensors of the self-study phase."""
    return {
        "self_study_volume": {
            "name": "Self-study determined volume",
            "endpoint": "getSLV",
            "unit": "L",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        "self_study_time": {
            "name": "Self-study determined time",
            "endpoint": "getSLT",
            "unit": "s",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        "self_study_flow": {
            "name": "Self-study determined flow",
            "endpoint": "getSLF",
            "unit": "L/h",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        "self_study_remaining": {
            "name": "Self-study remaining time",
            "endpoint": "getSLE",
            "unit": "s",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
    }


def build_profile_count_sensor(endpoint: str = "getPRN") -> dict[str, dict[str, Any]]:
    """Return the sensor that reports how many profiles the device has."""
    return {
        "profile_count": {
            "name": "Number of profiles",
            "endpoint": endpoint,
            "entity_category": EntityCategory.DIAGNOSTIC,
        }
    }


def build_network_sensors(
    *, lan: bool = True, wifi_scan: bool = True
) -> dict[str, dict[str, Any]]:
    """Return the network related diagnostic sensors."""
    sensors: dict[str, dict[str, Any]] = {
        "wifi_ssid": {
            "name": "Wifi SSID",
            "endpoint": "getWFC",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        "wlan_ip_address": {
            "name": "WLAN IP address",
            "endpoint": "getWIP",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        "wlan_gateway": {
            "name": "WLAN gateway",
            "endpoint": "getWGW",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
    }

    if wifi_scan:
        sensors["wifi_scan"] = {
            "name": "Wifi networks",
            "endpoint": "getWFL",
            "entity_category": EntityCategory.DIAGNOSTIC,
        }

    if lan:
        sensors.update(
            {
                "lan_ip_address": {
                    "name": "LAN IP address",
                    "endpoint": "getEIP",
                    "entity_category": EntityCategory.DIAGNOSTIC,
                },
                "lan_gateway": {
                    "name": "LAN gateway",
                    "endpoint": "getEGW",
                    "entity_category": EntityCategory.DIAGNOSTIC,
                },
                "mac_address_lan": {
                    "name": "MAC address LAN",
                    "endpoint": "getMAC2",
                    "entity_category": EntityCategory.DIAGNOSTIC,
                },
            }
        )

    return sensors


# ---------------------------------------------------------------------------
# Binary sensors
# ---------------------------------------------------------------------------
def build_alarm_binary_sensors(
    alarm_codes: dict[str, str], leakage_codes: list[str]
) -> dict[str, dict[str, Any]]:
    """Return the binary sensors that describe the alarm state."""
    return {
        "leakage_alarm": {
            "name": "Leakage alarm",
            "endpoint": "getALA",
            "device_class": BinarySensorDeviceClass.MOISTURE,
            "on_values": leakage_codes,
            "code_dict": alarm_codes,
        },
        "alarm_active": {
            "name": "Alarm active",
            "endpoint": "getALA",
            "device_class": PROBLEM,
            "off_values": ["FF"],
            "code_dict": alarm_codes,
        },
    }


def build_wifi_binary_sensor() -> dict[str, dict[str, Any]]:
    """Return the binary sensor that reports the WLAN connection state."""
    return {
        "wifi_connected": {
            "name": "Wifi connected",
            "endpoint": "getWFS",
            "device_class": BinarySensorDeviceClass.CONNECTIVITY,
            "on_values": ["2"],
        }
    }


def build_status_binary_sensors(
    warning_codes: dict[str, str] | None = None,
    notification_codes: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return the warning and notification binary sensors."""
    sensors: dict[str, dict[str, Any]] = {}

    if warning_codes is not None:
        sensors["warning_active"] = {
            "name": "Warning active",
            "endpoint": "getWRN",
            "device_class": PROBLEM,
            "off_values": ["FF"],
            "code_dict": warning_codes,
        }

    if notification_codes is not None:
        sensors["notification_active"] = {
            "name": "Notification active",
            "endpoint": "getNOT",
            "device_class": PROBLEM,
            "off_values": ["FF"],
            "code_dict": notification_codes,
        }

    return sensors


def build_microleakage_binary_sensor() -> dict[str, dict[str, Any]]:
    """Return the binary sensor that reports a running microleakage test."""
    return {
        "microleakage_active": {
            "name": "Microleakage test active",
            "endpoint": "getDSV",
            "on_values": ["1"],
        }
    }


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------
def build_profile_numbers(count: int = 8) -> dict[str, dict[str, Any]]:
    """Return the number entities of all profile settings."""
    numbers: dict[str, dict[str, Any]] = {}

    for profile in range(1, count + 1):
        numbers[f"profile_{profile}_volume"] = {
            "name": f"Profile {profile} permitted volume",
            "endpoint": f"getPV{profile}",
            "profile": profile,
            "service": "set_profile_volume",
            "field": "volume",
            "unit": "L",
            "min": 0,
            "max": 9000,
            "step": 1,
            "entity_category": EntityCategory.CONFIG,
        }
        numbers[f"profile_{profile}_time"] = {
            "name": f"Profile {profile} permitted time",
            "endpoint": f"getPT{profile}",
            "profile": profile,
            "service": "set_profile_time",
            "field": "minutes",
            "unit": "min",
            "min": 0,
            "max": 1500,
            "step": 1,
            "entity_category": EntityCategory.CONFIG,
        }
        numbers[f"profile_{profile}_flow"] = {
            "name": f"Profile {profile} permitted flow",
            "endpoint": f"getPF{profile}",
            "profile": profile,
            "service": "set_profile_flow",
            "field": "flow",
            "unit": "L/h",
            "min": 0,
            "max": 5000,
            "step": 1,
            "entity_category": EntityCategory.CONFIG,
        }
        numbers[f"profile_{profile}_return_time"] = {
            "name": f"Profile {profile} return time",
            "endpoint": f"getPR{profile}",
            "profile": profile,
            "service": "set_profile_return_time",
            "field": "hours",
            "unit": "h",
            "min": 0,
            "max": 700,
            "step": 1,
            "entity_category": EntityCategory.CONFIG,
        }

    return numbers
