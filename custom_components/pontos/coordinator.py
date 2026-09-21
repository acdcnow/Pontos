"""DataUpdateCoordinator for Pontos / SYR devices."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import TimestampDataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_FETCH_INTERVAL
from .const import CONF_HTTP_TIMEOUT
from .const import CONF_IP_ADDRESS
from .const import CONF_PORT
from .const import CONF_RETRY_ATTEMPTS
from .const import CONF_RETRY_DELAY
from .const import get_device_name
from .const import get_option
from .utils import build_urls
from .utils import fetch_data

_LOGGER = logging.getLogger(__name__)


class PontosDataUpdateCoordinator(TimestampDataUpdateCoordinator[dict[str, Any]]):
    """Coordinate the data polling of a single Pontos / SYR device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_const) -> None:
        """Initialise the coordinator from the config entry."""
        self.entry = entry
        self.device_const = device_const
        self.device_name = get_device_name(entry)
        self.ip_address: str = get_option(entry, CONF_IP_ADDRESS)
        self.port: int = get_option(entry, CONF_PORT)
        self.timeout: int = get_option(entry, CONF_HTTP_TIMEOUT)
        self.retry_attempts: int = get_option(entry, CONF_RETRY_ATTEMPTS)
        self.retry_delay: int = get_option(entry, CONF_RETRY_DELAY)

        # Serialises polling and commands, so a user triggered valve movement
        # is not interleaved with a poll of the same device.
        self.lock = asyncio.Lock()

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{self.device_name} coordinator",
            update_interval=timedelta(seconds=get_option(entry, CONF_FETCH_INTERVAL)),
        )

    @property
    def urls(self) -> list[str]:
        """Return the device specific URLs."""
        return build_urls(self.ip_address, self.device_const.URL_LIST, self.port)

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll all endpoints of the device."""
        if not self.ip_address:
            raise UpdateFailed("No IP address configured")

        async with self.lock:
            try:
                # The coordinator schedules the next poll itself, extra retries
                # inside the poll would delay every entity update.
                data = await fetch_data(
                    self.hass,
                    self.ip_address,
                    self.device_const.URL_LIST,
                    port=self.port,
                    timeout=self.timeout,
                    max_attempts=self.retry_attempts,
                    retry_delay=self.retry_delay,
                )
            except Exception as err:  # noqa: BLE001 - reported through the coordinator
                raise UpdateFailed(f"Error fetching data: {err}") from err

            if not data:
                raise UpdateFailed(
                    f"No data received from device at {self.ip_address}:{self.port}"
                )

            return data

    def is_stale(self, tolerance_minutes: int) -> bool:
        """Return True if the last successful poll is older than the tolerance."""
        if tolerance_minutes <= 0 or self.last_update_success_time is None:
            return False

        return dt_util.utcnow() - self.last_update_success_time > timedelta(
            minutes=tolerance_minutes
        )
