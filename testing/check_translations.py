"""Check the translation files against the flows, entities and services.

Home Assistant resolves flow labels with these paths::

    config.step.<step>.title / .description / .data.<field>
    config.step.<step>.sections.<section>.name / .data.<field>
    options.step.<step>.sections.<section>.data.<field>
    config.error.<key> / options.error.<key>

so a label that lives outside its section (for example in a flat
``options.step.init.data`` block) is never found and the UI shows the raw key.

This script imports the real flow code with stubbed Home Assistant modules,
derives the paths the flows actually need, and compares them with
``strings.json`` and every ``translations/<lang>.json``.  Missing keys in a non
English file are not an error: Home Assistant loads English first and overlays
the requested language on top of it.

Usage::

    python testing/check_translations.py
"""

from __future__ import annotations

import importlib
import json
import re
import sys
import types
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "custom_components" / "pontos"
FALLBACK_LANG = "en"

# Entity platform -> attribute of the device configuration modules.
PLATFORM_ATTRS = {
    "sensor": "SENSOR_DETAILS",
    "binary_sensor": "BINARY_SENSORS",
    "valve": "VALVES",
    "button": "BUTTONS",
    "select": "SELECTORS",
    "switch": "SWITCHES",
    "time": "TIME_ENTRIES",
}


# --------------------------------------------------------------------------- #
# Import the integration with stubbed Home Assistant modules
# --------------------------------------------------------------------------- #
class Dummy:
    """Placeholder for anything the integration imports from Home Assistant."""

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


def module(name: str, **attrs: Any) -> types.ModuleType:
    """Create a stub module that invents attributes on demand."""
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


class Section:
    """Mirror of ``homeassistant.data_entry_flow.section``."""

    def __init__(self, schema: Any, options: dict | None = None) -> None:
        self.schema = schema
        self.options = options or {}

    def __call__(self, value: Any) -> Any:
        return self.schema(value)


class _FlowBase:
    """Stand-in for ConfigFlow/OptionsFlow that skips their setup."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Accept the ``domain=`` keyword of ``ConfigFlow`` subclasses."""
        super().__init_subclass__()


class _AiohttpError(Exception):
    """Stand-in for ``aiohttp.ClientError``."""


def _install_stubs() -> None:
    aiohttp = module("aiohttp", ClientError=_AiohttpError)
    aiohttp.ClientTimeout = lambda **kwargs: ("ClientTimeout", kwargs)

    for name in (
        "homeassistant",
        "homeassistant.core",
        "homeassistant.const",
        "homeassistant.config_entries",
        "homeassistant.data_entry_flow",
        "homeassistant.helpers",
        "homeassistant.helpers.entity",
        "homeassistant.helpers.aiohttp_client",
        "homeassistant.helpers.selector",
        "homeassistant.components",
        "homeassistant.components.sensor",
        "homeassistant.components.binary_sensor",
        "homeassistant.components.valve",
    ):
        module(name)

    sys.modules["homeassistant.data_entry_flow"].section = Section
    sys.modules["homeassistant.core"].callback = lambda func: func
    sys.modules["homeassistant.core"].HomeAssistant = object
    sys.modules["homeassistant.config_entries"].ConfigEntry = object
    sys.modules["homeassistant.config_entries"].ConfigFlow = _FlowBase
    sys.modules["homeassistant.config_entries"].OptionsFlow = _FlowBase

    # Attach the sub modules to their parents (``import a.b`` style).
    for name, mod in list(sys.modules.items()):
        if name.startswith("homeassistant."):
            parent = sys.modules.get(name.rpartition(".")[0])
            if parent is not None:
                setattr(parent, name.rpartition(".")[2], mod)


def _import_package() -> tuple[types.ModuleType, types.ModuleType]:
    """Import the integration package under a neutral name."""
    _install_stubs()
    pkg = types.ModuleType("pontos_pkg")
    pkg.__path__ = [str(PKG)]
    sys.modules["pontos_pkg"] = pkg
    return (
        importlib.import_module("pontos_pkg.config_flow"),
        importlib.import_module("pontos_pkg.const"),
    )


# --------------------------------------------------------------------------- #
# Derive the required translation paths
# --------------------------------------------------------------------------- #
def _field_keys(schema: Any) -> set[str]:
    """Return the field keys of a schema, ignoring its sections."""
    keys: set[str] = set()
    for key, value in schema.schema.items():
        if isinstance(value, Section):
            continue
        keys.add(getattr(key, "schema", str(key)))
    return keys


def _section_keys(schema: Any) -> dict[str, set[str]]:
    """Return ``{section: {field, ...}}`` for the sections of a schema."""
    sections: dict[str, set[str]] = {}
    for key, value in schema.schema.items():
        if isinstance(value, Section):
            sections[str(getattr(key, "schema", key))] = _field_keys(value.schema)
    return sections


def _step_paths(schema: Any) -> tuple[set[str], set[str]]:
    """Return the required and the optional step relative paths."""
    required = set()
    optional = {"title", "description"}
    for key in _field_keys(schema):
        required.add(f"data.{key}")
    sections = _section_keys(schema)
    for section, keys in sections.items():
        required.add(f"sections.{section}.name")
        for key in keys:
            required.add(f"sections.{section}.data.{key}")
    if not sections:
        optional.add("data")
    return required, optional


def _flow_requirements(config_flow: types.ModuleType) -> dict[str, set[str]]:
    """Return every translation path the flows need, grouped by step."""
    handler = config_flow.PontosConfigFlow.__new__(config_flow.PontosConfigFlow)
    options_flow = config_flow.PontosOptionsFlow()

    requirements: dict[str, set[str]] = {}
    for step_id in ("user", "adopt_legacy"):
        required, _optional = _step_paths(handler._user_schema())
        requirements[f"config.step.{step_id}"] = required
    required, _optional = _step_paths(options_flow._options_schema())
    requirements["options.step.init"] = required

    source = (PKG / "config_flow.py").read_text(encoding="utf-8")
    for category in ("config", "options"):
        requirements[f"{category}.error"] = set(
            re.findall(r'errors\[[^\]]*\]\s*=\s*"([^"]+)"', source)
        )
    return requirements


def _entity_requirements(const: types.ModuleType) -> dict[str, set[str]]:
    """Return ``{platform: {key, ...}}`` for every entity of every device."""
    entities: dict[str, set[str]] = {platform: set() for platform in PLATFORM_ATTRS}
    for device_const in const.MAKES.values():
        for platform, attr in PLATFORM_ATTRS.items():
            entities[platform] |= set(getattr(device_const, attr, {}) or {})
    return {platform: keys for platform, keys in entities.items() if keys}


def _service_requirements() -> dict[str, bool]:
    """Return ``{service: has_name}`` parsed from ``services.yaml``."""
    text = (PKG / "services.yaml").read_text(encoding="utf-8")
    services: dict[str, bool] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith((" ", "\t", "-", "#")) or not line.strip():
            if current and re.match(r"^\s+name:", line):
                services[current] = True
            continue
        match = re.match(r"^([a-z0-9_]+):", line)
        if match:
            current = match.group(1)
            services.setdefault(current, False)
    return services


# --------------------------------------------------------------------------- #
# Compare with the translation files
# --------------------------------------------------------------------------- #
def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Return ``{dotted path: leaf}`` for a nested dict."""
    flat: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        flat[path] = value
        if isinstance(value, dict):
            flat.update(_flatten(value, path))
    return flat


def _has(flat: dict[str, Any], path: str) -> bool:
    """Return whether a path exists and holds a usable string."""
    return isinstance(flat.get(path), str) and bool(flat[path])


def _load_files() -> dict[str, dict[str, Any]]:
    """Return the translation files, English first."""
    files: dict[str, dict[str, Any]] = {}
    strings_file = PKG / "strings.json"
    if strings_file.is_file():
        files["strings.json"] = json.loads(strings_file.read_text(encoding="utf-8"))
    for path in sorted((PKG / "translations").glob("*.json")):
        files[f"translations/{path.name}"] = json.loads(
            path.read_text(encoding="utf-8")
        )
    return files


def main() -> int:
    config_flow, const = _import_package()
    requirements = _flow_requirements(config_flow)
    entities = _entity_requirements(const)
    services = _service_requirements()
    files = _load_files()

    print("=== files ===")
    for name, data in files.items():
        print(f"  {name:26} title: {data.get('title')!r}")
    print()

    print("=== flow paths the code needs ===")
    for group, paths in sorted(requirements.items()):
        print(f"  {group:24} {len(paths)} path(s)")
    print()

    failures: list[str] = []

    # 1. Every language must define the flow paths in the right place.
    print("=== flow translations ===")
    for name, data in files.items():
        flat = _flatten(data)
        missing = sorted(
            {
                f"{group}.{path}"
                for group, paths in requirements.items()
                for path in paths
                if not _has(flat, f"{group}.{path}")
            }
        )
        is_source = name == "strings.json" or name.endswith("/en.json")
        status = (
            "OK"
            if not missing
            else ("MISSING" if is_source else "incomplete (falls back to English)")
        )
        print(f"  {name:26} {status}")
        if missing and is_source:
            for path in missing:
                print(f"      - {path}")
            failures.append(f"{name} misses {len(missing)} flow path(s)")
        elif missing:
            print(f"      {len(missing)} path(s) untranslated, English is used instead")

    # 2. strings.json and translations/en.json must stay identical.
    if "strings.json" in files and "translations/en.json" in files:
        if files["strings.json"] != files["translations/en.json"]:
            failures.append("strings.json differs from translations/en.json")
            print("  strings.json differs from translations/en.json")

    # 3. English must name every entity of every device.
    print()
    print("=== entity translations (en) ===")
    en_flat = _flatten(files.get("translations/en.json", {}))
    for platform, keys in sorted(entities.items()):
        missing = sorted(
            key
            for key in keys
            if not _has(en_flat, f"entity.{platform}.{key}.name")
            and not _has(en_flat, f"entity.{platform}.{key}")
        )
        print(f"  entity.{platform:14} {len(keys)} key(s), missing: {len(missing)}")
        if missing:
            print(f"      {missing}")
            failures.append(f"entity.{platform} misses {len(missing)} name(s)")

    # 4. Every service needs a name, either in services.yaml or in en.json.
    print()
    print("=== services ===")
    for service, has_name in sorted(services.items()):
        translated = _has(en_flat, f"services.{service}.name") or _has(
            en_flat, f"services.{service}"
        )
        if not has_name and not translated:
            failures.append(f"service {service} has no name")
            print(f"  {service:28} no name in services.yaml and no translation")
    print(
        f"  {len(services)} service(s), named in services.yaml: "
        f"{sum(1 for value in services.values() if value)}"
    )

    # 5. Non English files should not invent keys that English does not have.
    print()
    print("=== unknown keys in other languages ===")
    for name, data in files.items():
        if name.endswith("/en.json") or name == "strings.json":
            continue
        extra = sorted(
            path
            for path, value in _flatten(data).items()
            if path not in en_flat and not isinstance(value, dict)
        )
        print(f"  {name:26} {len(extra)} key(s) not in en")
        if extra:
            print(f"      {extra[:10]}")

    print()
    if failures:
        print(f"RESULT: {len(failures)} problem(s)")
        for failure in failures:
            print(" -", failure)
        return 1

    print("RESULT: flows, entities and services are translated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
