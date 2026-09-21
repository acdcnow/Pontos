"""Profile selection for the Pontos / SYR integration."""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError

from .control import PontosControlEntity
from .coordinator import PontosDataUpdateCoordinator
from .device import profile_limit

LOGGER = logging.getLogger(__name__)

#: Sensor that reports the number of the active profile.
ACTIVE_PROFILE_SENSOR = "active_profile"

#: Sensor key pattern of the profile names.
PROFILE_NAME_SENSOR = "profile_{profile}"

#: Service that activates a profile.
SET_PROFILE_SERVICE = "set_profile"


class PontosProfileSelect(PontosControlEntity, SelectEntity):
    """Dropdown that shows the profiles of the device by name.

    The device reports the active profile as a number and the profile names in
    separate endpoints, so the labels are built from both values. The labels
    used to come from the entity registry, which never contained the guessed
    unique ids, so the dropdown stayed empty and unavailable.
    """

    def __init__(
        self,
        entry: ConfigEntry,
        identifier: str,
        device_info: dict[str, Any],
        coordinator: PontosDataUpdateCoordinator,
        key: str,
        config: dict[str, Any],
    ) -> None:
        """Initialise the profile dropdown."""
        source_config = dict(config)
        source_config.setdefault("sensor", ACTIVE_PROFILE_SENSOR)
        super().__init__(
            entry, identifier, device_info, coordinator, key, source_config
        )

    # ------------------------------------------------------------------
    # The profiles of the device
    # ------------------------------------------------------------------
    def _labels(self) -> dict[int, str]:
        """Return the label of every profile the device reports.

        Duplicated names get their number appended, otherwise the dropdown
        would not be able to tell them apart.
        """
        details_map: dict[str, Any] = getattr(self._device_const, "SENSOR_DETAILS", {})
        data = self.coordinator.data or {}
        names: dict[int, str] = {}

        for profile in range(
            1, profile_limit(self._device_const, self.coordinator) + 1
        ):
            name = ""
            details = details_map.get(PROFILE_NAME_SENSOR.format(profile=profile)) or {}
            if endpoint := details.get("endpoint"):
                if (raw := data.get(endpoint)) is not None:
                    name = str(raw).strip()
                    if "ERROR" in name.upper():
                        name = ""

            names[profile] = name or f"Profile {profile}"

        counts = Counter(names.values())
        return {
            profile: (f"{name} ({profile})" if counts[name] > 1 else name)
            for profile, name in names.items()
        }

    def _active_profile(self) -> int | None:
        """Return the number of the profile the device reports as active."""
        if (number := self._source_number()) is None:
            return None

        return int(number)

    # ------------------------------------------------------------------
    # SelectEntity
    # ------------------------------------------------------------------
    @property
    def options(self) -> list[str]:
        """Return the profile names."""
        return list(self._labels().values())

    @property
    def current_option(self) -> str | None:
        """Return the name of the active profile."""
        if (profile := self._active_profile()) is None:
            return None

        return self._labels().get(profile)

    async def async_select_option(self, option: str) -> None:
        """Activate the selected profile."""
        profile = next(
            (
                code
                for code, label in self._labels().items()
                if label == str(option).strip()
            ),
            None,
        )
        if profile is None:
            raise HomeAssistantError(f"'{option}' is not one of the profiles")

        LOGGER.debug("Activating profile %s (%s)", profile, option)
        await self._call_service(SET_PROFILE_SERVICE, profile)
