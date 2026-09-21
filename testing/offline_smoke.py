#!/usr/bin/env python3
"""Offline smoke test: run the integration without Home Assistant.

This executes the real code of the integration with stubbed Home Assistant
imports, using the device payloads from `testing/*.json`. It catches the kind of
error that only appears at runtime - wrong container types, signature mismatches,
deadlocks between the poller and the service calls - which no linter can see and
which needs a full Home Assistant installation to notice otherwise.

    python3 offline_smoke.py
    python3 offline_smoke.py --make "SYR NeoSoft"

Exit code 0 means: every device type sets up, creates its entities, answers
service calls and unloads cleanly.
"""

from __future__ import annotations

import argparse
import asyncio
import faulthandler
import importlib
import json
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Generic, TypeVar

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "custom_components" / "pontos"
TESTING = REPO / "testing"

#: Device family -> payload of the simulator that speaks its protocol.
FIXTURES = {
    "Hansgrohe Pontos": "pontos.json",
    "SYR Trio": "safetech.json",
    "SYR SafeTech+": "safetech.json",
    "SYR SafeTech+ (Old firmware)": "safetech_v4.json",
    "SYR NeoSoft": "neosoft.json",
}

#: Services that need a value and a profile, used to check the URL that is built.
PROFILE_SERVICES = {
    "set_profile": {"profile": 2},
    "set_profile_volume": {"profile": 3, "volume": 250},
    "set_profile_time": {"profile": 2, "minutes": 45},
    "set_profile_flow": {"profile": 1, "flow": 900},
    "set_profile_return_time": {"profile": 4, "hours": 12},
    "set_profile_availability": {"profile": 1, "enabled": True},
    "set_profile_warning": {"profile": 1, "enabled": False},
    "start_self_study": {"days": 3},
    "microleakage_schedule": {"schedule": 2},
    "microleakage_time": {"time": "03:30"},
    "set_regeneration_mode": {"mode": 2},
    "set_regeneration_interval": {"days": 2},
    "set_regeneration_time": {"time": "02:00"},
}

#: Services without arguments, only the target fields.
SIMPLE_SERVICES = (
    "open_valve",
    "close_valve",
    "clear_alarms",
    "clear_warnings",
    "clear_notifications",
    "enable_buzzer",
    "disable_buzzer",
    "microleakage_test",
    "delete_self_study",
)

MAX_ENTITIES = 2000
T = TypeVar("T")


def phase(message: str, indent: int = 0) -> None:
    """Print a progress line immediately."""
    print(f"{'  ' * indent}{message}", flush=True)


# ---------------------------------------------------------------------------
# Stubs for the Home Assistant imports of the integration
# ---------------------------------------------------------------------------
class Dummy:
    """Recursive stand-in for HA enums, classes and helper functions."""

    _cache: dict[tuple[str, str], "Dummy"] = {}

    def __init__(self, name: str) -> None:
        self.__name__ = name

    def __getattr__(self, attr: str) -> "Dummy":
        if attr.startswith("__"):
            raise AttributeError(attr)
        key = (self.__name__, attr)
        if key not in Dummy._cache:
            Dummy._cache[key] = Dummy(f"{self.__name__}.{attr}")
        return Dummy._cache[key]

    def __call__(self, *args: Any, **kwargs: Any) -> "Dummy":
        return Dummy(f"{self.__name__}()")

    def __repr__(self) -> str:
        return f"<{self.__name__}>"


def stub_module(name: str, **attrs: Any) -> types.ModuleType:
    """Create a stub module that answers every attribute with a Dummy."""
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)

    def _getattr(attr: str) -> Any:
        if attr.startswith("__"):
            raise AttributeError(attr)
        key = (name, attr)
        if key not in Dummy._cache:
            Dummy._cache[key] = Dummy(f"{name}.{attr}")
        return Dummy._cache[key]

    mod.__getattr__ = _getattr  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


class AiohttpError(Exception):
    """Stand-in for aiohttp.ClientError."""


class Entity:
    """Minimal Home Assistant entity."""

    _attr_has_entity_name = False
    hass: Any = None

    @property
    def extra_state_attributes(self) -> Any:
        """Return no extra attributes."""
        return None

    async def async_added_to_hass(self) -> None:
        """Do nothing."""

    def async_write_ha_state(self) -> None:
        """Do nothing."""

    def async_on_remove(self, func: Any) -> None:
        """Ignore removal callbacks."""


class CoordinatorEntity(Generic[T]):
    """Minimal CoordinatorEntity."""

    hass: Any = None

    def __init__(self, coordinator: T | None = None, context: Any = None) -> None:
        """Store the coordinator."""
        self.coordinator = coordinator

    @property
    def extra_state_attributes(self) -> Any:
        """Return no extra attributes."""
        return None

    @property
    def available(self) -> bool:
        """Always available."""
        return True

    def _handle_coordinator_update(self) -> None:
        """Do nothing."""

    async def async_added_to_hass(self) -> None:
        """Do nothing."""

    def async_write_ha_state(self) -> None:
        """Do nothing."""

    def async_on_remove(self, func: Any) -> None:
        """Ignore removal callbacks."""


class SensorEntity(Entity):
    """Minimal sensor entity."""

    @property
    def native_value(self) -> Any:
        """Return no value."""
        return None


class RestoreSensor(SensorEntity):
    """Minimal RestoreSensor."""

    async def async_get_last_sensor_data(self) -> Any:
        """Return no restored data."""
        return None


class TimestampDataUpdateCoordinator(Generic[T]):
    """Minimal TimestampDataUpdateCoordinator."""

    def __init__(self, hass: Any = None, *args: Any, **kwargs: Any) -> None:
        """Initialise the coordinator."""
        self.hass = hass
        self.data: Any = None
        self.last_update_success_time: Any = None

    async def async_config_entry_first_refresh(self) -> None:
        """Fetch the first payload."""
        self.data = await self._async_update_data()

    async def async_refresh(self) -> None:
        """Fetch a new payload."""
        self.data = await self._async_update_data()


class DeviceInfo(dict):
    """DeviceInfo is a TypedDict, a plain dict is close enough."""


def install_stubs() -> None:
    """Register the stub modules."""
    aiohttp = stub_module("aiohttp", ClientError=AiohttpError)
    aiohttp.ClientTimeout = lambda **kwargs: ("ClientTimeout", kwargs)

    for name in (
        "homeassistant",
        "homeassistant.core",
        "homeassistant.const",
        "homeassistant.config_entries",
        "homeassistant.data_entry_flow",
        "homeassistant.exceptions",
        "homeassistant.helpers",
        "homeassistant.helpers.entity",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.entity_registry",
        "homeassistant.helpers.event",
        "homeassistant.helpers.restore_state",
        "homeassistant.helpers.service",
        "homeassistant.helpers.selector",
        "homeassistant.helpers.device_registry",
        "homeassistant.helpers.aiohttp_client",
        "homeassistant.helpers.update_coordinator",
        "homeassistant.helpers.config_validation",
        "homeassistant.components",
        "homeassistant.components.sensor",
        "homeassistant.components.binary_sensor",
        "homeassistant.components.number",
        "homeassistant.components.button",
        "homeassistant.components.select",
        "homeassistant.components.switch",
        "homeassistant.components.time",
        "homeassistant.components.valve",
    ):
        stub_module(name)

    core = sys.modules["homeassistant.core"]
    core.HomeAssistant = object
    core.callback = lambda func: func
    core.ServiceCall = Dummy("ServiceCall")

    exceptions = sys.modules["homeassistant.exceptions"]
    for error in (
        "HomeAssistantError",
        "ServiceValidationError",
        "ConfigEntryNotReady",
    ):
        setattr(exceptions, error, type(error, (Exception,), {}))

    helpers = sys.modules["homeassistant.helpers.entity"]
    helpers.Entity = Entity
    sys.modules[
        "homeassistant.helpers.entity_platform"
    ].AddConfigEntryEntitiesCallback = Dummy("AddConfigEntryEntitiesCallback")

    update_coordinator = sys.modules["homeassistant.helpers.update_coordinator"]
    update_coordinator.CoordinatorEntity = CoordinatorEntity
    update_coordinator.UpdateFailed = type("UpdateFailed", (Exception,), {})
    update_coordinator.TimestampDataUpdateCoordinator = TimestampDataUpdateCoordinator

    sensor = sys.modules["homeassistant.components.sensor"]
    sensor.SensorEntity = SensorEntity
    sensor.RestoreSensor = RestoreSensor
    sys.modules["homeassistant.components.binary_sensor"].BinarySensorEntity = type(
        "BinarySensorEntity", (Entity,), {}
    )
    sys.modules["homeassistant.components.number"].NumberEntity = type(
        "NumberEntity", (Entity,), {}
    )
    for name, attribute in (
        ("button", "ButtonEntity"),
        ("select", "SelectEntity"),
        ("switch", "SwitchEntity"),
        ("time", "TimeEntity"),
        ("valve", "ValveEntity"),
    ):
        setattr(
            sys.modules[f"homeassistant.components.{name}"],
            attribute,
            type(attribute, (Entity,), {}),
        )

    device_registry = sys.modules["homeassistant.helpers.device_registry"]
    device_registry.DeviceInfo = DeviceInfo
    device_registry.CONNECTION_NETWORK_MAC = "mac"
    device_registry.async_get = lambda hass: hass.device_registry

    util = stub_module("homeassistant.util")

    def slugify(text: str) -> str:
        import re

        return re.sub(r"[^a-z0-9_]+", "_", str(text).lower()).strip("_")

    util.slugify = slugify
    stub_module("homeassistant.util.dt").utcnow = lambda: datetime.now(UTC)

    for name, mod in list(sys.modules.items()):
        if name.startswith("homeassistant."):
            parent = sys.modules.get(name.rpartition(".")[0])
            if parent is not None:
                setattr(parent, name.rpartition(".")[2], mod)


# ---------------------------------------------------------------------------
# Minimal Home Assistant runtime
# ---------------------------------------------------------------------------
class FakeStates:
    """State machine that knows the entities the integration creates."""

    def __init__(self) -> None:
        self._states: dict[str, Any] = {}

    def set(
        self, entity_id: str, state: str, attributes: dict[str, Any] | None = None
    ) -> None:
        """Add a state."""
        self._states[entity_id] = types.SimpleNamespace(
            entity_id=entity_id, state=state, attributes=attributes or {}
        )

    def get(self, entity_id: str) -> Any:
        """Return a state."""
        return self._states.get(entity_id)

    def is_state(self, entity_id: str, state: str) -> bool:
        """Compare a state."""
        current = self._states.get(entity_id)
        return current is not None and current.state == state


class FakeDevice:
    """Device registry entry."""

    def __init__(
        self, device_id: str, config_entry_id: str, identifiers: Any = ()
    ) -> None:
        """Store the ids."""
        self.id = device_id
        self.config_entry_id = config_entry_id
        self.identifiers = tuple(identifiers)
        self.data: dict[str, Any] = {}


class FakeDeviceRegistry:
    """Device registry."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.devices: dict[str, FakeDevice] = {}

    def async_get(self, device_id: str) -> FakeDevice | None:
        """Return a device."""
        return self.devices.get(device_id)

    def async_get_or_create(self, **kwargs: Any) -> FakeDevice:
        """Return the device for these identifiers, creating it if needed."""
        identifiers = tuple(sorted(map(tuple, kwargs.get("identifiers") or ())))
        for device in self.devices.values():
            if device.identifiers == identifiers:
                return device

        self.created.append(kwargs)
        device = FakeDevice(
            f"device{len(self.devices) + 1}", kwargs["config_entry_id"], identifiers
        )
        device.data = kwargs
        self.devices[device.id] = device
        return device


class FakeServices:
    """Service registry."""

    def __init__(self, hass: "FakeHass") -> None:
        self.hass = hass
        self.registered: dict[tuple[str, str], Any] = {}

    def async_register(
        self, domain: str, service: str, handler: Any, schema: Any = None
    ) -> None:
        """Register a service."""
        self.registered[(domain, service)] = handler

    def has_service(self, domain: str, service: str) -> bool:
        """Return whether a service is registered."""
        return (domain, service) in self.registered

    def async_remove(self, domain: str, service: str) -> None:
        """Remove a service."""
        self.registered.pop((domain, service), None)

    async def async_call(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any] | None = None,
        blocking: bool = False,
        context: Any = None,
        target: dict[str, Any] | None = None,
        return_response: bool = False,
    ) -> Any:
        """Call a registered service, like the entities do."""
        data = dict(service_data or {})
        for key, value in (target or {}).items():
            if isinstance(value, list) and len(value) == 1:
                data.setdefault(key, value[0])
            else:
                data.setdefault(key, value)
        handler = self.registered.get((domain, service))
        if handler is None:
            raise sys.modules["homeassistant.exceptions"].ServiceValidationError(
                f"Service {domain}.{service} is not registered"
            )
        await handler(
            types.SimpleNamespace(data=data, service=service, context=context)
        )
        return None


class FakeEntry:
    """Config entry."""

    def __init__(self, make: str, const: Any) -> None:
        self.entry_id = "entry1"
        self.domain = const.DOMAIN
        self.title = "Wasser"
        self.data = {const.CONF_DEVICE_NAME: "Wasser", const.CONF_MAKE: make}
        self.options = {
            const.CONF_IP_ADDRESS: "192.168.1.100",
            const.CONF_PORT: 5333,
            const.CONF_FETCH_INTERVAL: 10,
            const.CONF_ENABLE_DIAGNOSTICS: True,
            const.CONF_ENABLE_CONTROLS: True,
            const.CONF_IGNORE_INVALID_VALUES: True,
            const.CONF_STALE_TOLERANCE: 60,
            const.CONF_VOLUME_UNIT: "L",
        }

    def add_update_listener(self, listener: Any) -> Any:
        """Accept an update listener."""
        return lambda: None

    def async_on_unload(self, func: Any) -> None:
        """Ignore unload callbacks."""


class FakeConfigEntries:
    """Config entry manager that forwards platforms like Home Assistant."""

    def __init__(self, hass: "FakeHass") -> None:
        self.hass = hass
        self.entities: dict[str, list[Any]] = {}
        self.forwarded: list[str] = []
        self.endless_generator: list[str] = []

    async def async_forward_entry_setups(
        self, entry: FakeEntry, platforms: list[str]
    ) -> None:
        """Set up every platform of an entry."""
        self.forwarded.extend(platforms)
        for platform in platforms:
            platform_mod = importlib.import_module(f"pontos_pkg.{platform}")
            self.entities.setdefault(platform, [])

            def add(entities: Any, *args: Any, **kwargs: Any) -> None:
                # Bounded: an endless generator would hang the test.
                collected = []
                for entity in entities:
                    entity.hass = self.hass
                    # Home Assistant registers the device of an entity itself, so
                    # the harness does the same to see which device it lands on.
                    if (
                        device_info := getattr(entity, "device_info", None)
                    ) is not None:
                        self.hass.device_registry.async_get_or_create(
                            config_entry_id=entry.entry_id, **device_info
                        )
                    collected.append(entity)
                    if len(collected) >= MAX_ENTITIES:
                        self.endless_generator.append(platform)
                        break
                self.entities[platform].extend(collected)

            await platform_mod.async_setup_entry(self.hass, entry, add)

    async def async_unload_platforms(
        self, entry: FakeEntry, platforms: list[str]
    ) -> bool:
        """Unload, always successfully."""
        return True

    def async_get_entry(self, entry_id: str) -> Any:
        """Return the single test entry."""
        return self.hass.entry if self.hass.entry.entry_id == entry_id else None


class FakeHass:
    """The Home Assistant object the integration sees."""

    def __init__(self, make: str, const: Any) -> None:
        self.data: dict[str, Any] = {}
        self.states = FakeStates()
        self.services = FakeServices(self)
        self.config_entries = FakeConfigEntries(self)
        self.device_registry = FakeDeviceRegistry()
        self.bus = types.SimpleNamespace(async_listen=lambda *a, **k: (lambda: None))
        self.entry = FakeEntry(make, const)


# ---------------------------------------------------------------------------
# The test itself
# ---------------------------------------------------------------------------
async def check_make(
    make: str, module: Any, const: Any, services_mod: Any
) -> list[str]:
    """Set up one device type and exercise it."""
    failures: list[str] = []
    hass = FakeHass(make, const)
    entry = hass.entry
    calls: list[tuple[str, dict[str, Any]]] = []

    payload: dict[str, Any] = json.loads(
        (TESTING / FIXTURES[make]).read_text(encoding="utf-8")
    )

    # The device itself is simulated, everything else is the real code.
    async def fake_fetch_data(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return payload

    async def fake_send_command(
        hass: Any,
        ip: str,
        base_url: str,
        endpoint: str,
        payload: Any = None,
        **kwargs: Any,
    ) -> bool:
        calls.append((endpoint, payload or {}))
        return True

    module.coordinator.fetch_data = fake_fetch_data
    services_mod.send_command = fake_send_command

    try:
        result = await asyncio.wait_for(module.async_setup_entry(hass, entry), 15)
    except TimeoutError:
        return [f"{make}: async_setup_entry did not finish within 15s"]
    except Exception as err:  # noqa: BLE001 - the point of the test
        return [f"{make}: async_setup_entry raised {err!r}"]

    if result is not True:
        failures.append(f"{make}: async_setup_entry returned {result!r}")

    registered = hass.services.registered
    if not registered:
        failures.append(f"{make}: no services registered")
    if not hass.device_registry.created:
        failures.append(f"{make}: the device was not registered")

    total = sum(len(entities) for entities in hass.config_entries.entities.values())
    phase(
        f"{make}: {total} entities, {len(registered)} services,"
        f" {len(hass.device_registry.devices)} device(s),"
        f" platforms {hass.config_entries.forwarded}"
    )
    if total == 0:
        failures.append(f"{make}: no entities were created")
    if hass.config_entries.endless_generator:
        failures.append(
            f"{make}: endless entity generator in {hass.config_entries.endless_generator}"
        )

    # Unique ids and names, so entities survive a restart and can be renamed.
    for platform, entities in hass.config_entries.entities.items():
        for entity in entities:
            key = getattr(entity, "_key", None) or getattr(entity, "_attr_name", "?")
            if not getattr(entity, "_attr_unique_id", None):
                failures.append(f"{make}: {platform}.{key} has no unique id")
            if not entity._attr_has_entity_name:
                failures.append(
                    f"{make}: {platform}.{key} does not use the device name"
                )
            if not (
                getattr(entity, "_attr_translation_key", None)
                or getattr(entity, "_attr_name", None)
            ):
                failures.append(f"{make}: {platform}.{key} has no name")

    # Entity properties have to be readable, this is what the UI does.
    for platform, entities in hass.config_entries.entities.items():
        for entity in entities:
            key = getattr(entity, "_key", None) or "?"
            try:
                await asyncio.wait_for(entity.async_added_to_hass(), 5)
                getattr(entity, "native_value", None)
                getattr(entity, "extra_state_attributes", None)
                getattr(entity, "available", None)
            except TimeoutError:
                failures.append(f"{make}: {platform}.{key} async_added_to_hass hung")
            except Exception as err:  # noqa: BLE001
                failures.append(f"{make}: {platform}.{key} properties raised {err!r}")

    # The controls have to be usable: an entity that cannot find the sensor it
    # mirrors stays greyed out in the UI. The settings also have to live on the
    # separate configuration device, so the meter stays about its measurements.
    entry_data = hass.data[const.DOMAIN]["entries"][entry.entry_id]
    control_platforms = {"button", "number", "select", "switch", "time"}
    setting_platforms = {"number", "switch", "time"}
    meter_identifiers = set(entry_data["device_info"]["identifiers"])
    config_identifiers = set(entry_data["config_device_info"]["identifiers"])
    needs_config_device = False
    config_device_registered = False
    controls_checked = 0

    for platform, entities in hass.config_entries.entities.items():
        if platform not in control_platforms:
            continue

        for entity in entities:
            controls_checked += 1
            key = (
                getattr(entity, "_key", None)
                or getattr(entity, "_attr_name", None)
                or getattr(entity, "_endpoint", "?")
            )
            config = getattr(entity, "_config", {})
            reference = config.get("sensor") or config.get("availability_sensor")
            if reference and not getattr(entity, "_source_endpoint", None):
                failures.append(
                    f"{make}: {platform}.{key} cannot find the sensor '{reference}'"
                )
            if entity.available is not True:
                failures.append(f"{make}: {platform}.{key} is unavailable")

            # The profile selection and the buttons control the meter, the
            # settings get their own device.
            settings = platform in setting_platforms or (
                platform == "select" and key != "profile_select"
            )
            expected = config_identifiers if settings else meter_identifiers
            if settings:
                needs_config_device = True

            identifiers = set((entity.device_info or {}).get("identifiers") or ())
            if identifiers != expected:
                failures.append(
                    f"{make}: {platform}.{key} belongs to {sorted(identifiers)},"
                    f" expected {sorted(expected)}"
                )

    for created in hass.device_registry.created:
        if set(created.get("identifiers") or ()) == config_identifiers:
            config_device_registered = True
            if created.get("via_device_id") != entry_data["device_id"]:
                failures.append(
                    f"{make}: the configuration device is not linked to the meter"
                )

    if needs_config_device and not config_device_registered:
        failures.append(f"{make}: the configuration device was not created")

    phase(
        f"{make}: {controls_checked} control(s) usable, settings on"
        f" '{entry_data['config_device_info']['name']}'",
        indent=1,
    )

    # Service calls build the documented URLs and refresh the coordinator.
    device_const = const.get_device_const(entry)
    base = device_const.BASE_URL.format(ip="192.168.1.100", port=5333)
    available_services = getattr(device_const, "SERVICES", {})

    for service_name, extra in PROFILE_SERVICES.items():
        if service_name not in available_services:
            continue
        data = dict(extra)
        data[services_mod.ATTR_ENTRY_ID] = entry.entry_id
        handler = registered[(const.DOMAIN, service_name)]
        try:
            await asyncio.wait_for(
                handler(
                    types.SimpleNamespace(data=data, service=service_name, context=None)
                ),
                10,
            )
        except TimeoutError:
            failures.append(f"{make}: {service_name} deadlocked")
            continue
        except Exception as err:  # noqa: BLE001
            failures.append(f"{make}: {service_name} raised {err!r}")
            continue

        endpoint, values = calls[-1]
        try:
            url = f"{base}{endpoint.format(**values)}"
        except KeyError as err:
            failures.append(f"{make}: {service_name} cannot format its URL ({err})")
            continue
        if "{" in url or "}" in url:
            failures.append(f"{make}: {service_name} left a placeholder in {url}")
        # The device expects the JSON literals, not the Python spelling.
        if "/True" in url or "/False" in url:
            failures.append(f"{make}: {service_name} sent a Python boolean: {url}")
        phase(f"  {service_name:26} {url}", indent=1)

    for service_name in SIMPLE_SERVICES:
        if service_name not in available_services:
            continue
        data = {services_mod.ATTR_ENTRY_ID: entry.entry_id}
        handler = registered[(const.DOMAIN, service_name)]
        try:
            await asyncio.wait_for(
                handler(
                    types.SimpleNamespace(data=data, service=service_name, context=None)
                ),
                10,
            )
        except TimeoutError:
            failures.append(f"{make}: {service_name} deadlocked")
            continue
        except Exception as err:  # noqa: BLE001
            failures.append(f"{make}: {service_name} raised {err!r}")
            continue
        endpoint, values = calls[-1]
        phase(f"  {service_name:26} {base}{endpoint.format(**values)}", indent=1)

    # A service the model does not offer must be reported, not silently ignored.
    for service_name in ("set_regeneration_mode", "start_self_study"):
        if service_name in available_services:
            continue
        handler = registered[(const.DOMAIN, service_name)]
        call = types.SimpleNamespace(
            data={
                "mode": 2,
                "days": 3,
                services_mod.ATTR_ENTRY_ID: entry.entry_id,
            },
            service=service_name,
            context=None,
        )
        try:
            await asyncio.wait_for(handler(call), 10)
            failures.append(f"{make}: unsupported {service_name} was accepted")
        except sys.modules["homeassistant.exceptions"].ServiceValidationError:
            phase(f"  {service_name} correctly reported as unsupported", indent=1)
        except Exception as err:  # noqa: BLE001
            failures.append(f"{make}: unsupported {service_name} raised {err!r}")

    # Writing through a number entity must not deadlock the command lock.
    numbers = hass.config_entries.entities.get("number", [])
    if numbers:
        try:
            await asyncio.wait_for(numbers[0].async_set_native_value(250), 10)
        except TimeoutError:
            failures.append(f"{make}: writing a number entity deadlocked")
        except Exception as err:  # noqa: BLE001
            failures.append(f"{make}: writing a number entity raised {err!r}")

    try:
        unloaded = await asyncio.wait_for(module.async_unload_entry(hass, entry), 10)
    except TimeoutError:
        failures.append(f"{make}: async_unload_entry did not finish within 10s")
        return failures
    except Exception as err:  # noqa: BLE001
        failures.append(f"{make}: async_unload_entry raised {err!r}")
        return failures

    if unloaded is not True:
        failures.append(f"{make}: async_unload_entry returned {unloaded!r}")
    if registered:
        failures.append(f"{make}: {len(registered)} services left after unload")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--make", choices=list(FIXTURES), help="check one device type")
    parser.add_argument(
        "--timeout", type=int, default=120, help="watchdog for the whole run"
    )
    args = parser.parse_args()

    faulthandler.dump_traceback_later(args.timeout, exit=True)
    install_stubs()

    pkg = types.ModuleType("pontos_pkg")
    pkg.__path__ = [str(PKG)]
    pkg.__package__ = "pontos_pkg"
    sys.modules["pontos_pkg"] = pkg
    # Execute the integration's __init__.py inside the package namespace.
    exec(
        compile(
            (PKG / "__init__.py").read_text(encoding="utf-8"),
            str(PKG / "__init__.py"),
            "exec",
        ),
        pkg.__dict__,
    )

    coordinator_mod = importlib.import_module("pontos_pkg.coordinator")
    services_mod = importlib.import_module("pontos_pkg.services")
    const = importlib.import_module("pontos_pkg.const")
    module = types.SimpleNamespace(
        async_setup_entry=pkg.async_setup_entry,
        async_unload_entry=pkg.async_unload_entry,
        coordinator=coordinator_mod,
    )

    makes = [args.make] if args.make else list(FIXTURES)
    failures: list[str] = []
    for make in makes:
        phase(f"=== {make} ===")
        result = asyncio.run(check_make(make, module, const, services_mod))
        failures.extend(result)
        phase("")

    if failures:
        print(f"RESULT: {len(failures)} failure(s)")
        for failure in failures:
            print(" -", failure)
        return 1

    print(
        "RESULT: every device type sets up, creates entities, answers services and unloads"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
