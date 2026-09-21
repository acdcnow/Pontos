"""Helpers to talk to Pontos / SYR devices through their local HTTP API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_HTTP_TIMEOUT
from .const import DEFAULT_PORT
from .const import DEFAULT_RETRY_DELAY

_LOGGER = logging.getLogger(__name__)


def build_urls(ip_address: str, url_list: str | list[str], port: int) -> list[str]:
    """Expand the device specific URL templates into full URLs."""
    if isinstance(url_list, str):
        url_list = [url_list]

    return [url.format(ip=ip_address, port=port) for url in url_list]


async def fetch_data(
    hass: HomeAssistant,
    ip_address: str,
    url_list: str | list[str],
    port: int = DEFAULT_PORT,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
    max_attempts: int = 1,
    retry_delay: int = DEFAULT_RETRY_DELAY,
) -> dict[str, Any]:
    """Fetch all URLs of a device and merge the responses.

    A single failing endpoint no longer discards the data of the other
    endpoints. An empty result means that no endpoint answered at all.
    """
    urls = build_urls(ip_address, url_list, port)
    session = async_get_clientsession(hass)
    client_timeout = ClientTimeout(total=timeout)

    data: dict[str, Any] = {}
    errors: list[str] = []

    for attempt in range(1, max_attempts + 1):
        data = {}
        errors = []

        for url in urls:
            try:
                async with session.get(url, timeout=client_timeout) as response:
                    if response.status != 200:
                        errors.append(f"{url}: HTTP {response.status}")
                        continue

                    payload = await response.json(content_type=None)
                    if isinstance(payload, dict):
                        data.update(payload)
                    else:
                        errors.append(f"{url}: unexpected payload {type(payload).__name__}")
            except TimeoutError:
                errors.append(f"{url}: request timed out after {timeout}s")
            except ClientError as err:
                errors.append(f"{url}: {err}")
            except ValueError as err:
                # Malformed JSON payload
                errors.append(f"{url}: invalid JSON ({err})")

        if not errors:
            return data

        if attempt < max_attempts:
            delay = retry_delay * attempt
            _LOGGER.warning(
                "Attempt %s/%s for %s failed (%s), retrying in %ss",
                attempt,
                max_attempts,
                ip_address,
                "; ".join(errors),
                delay,
            )
            await asyncio.sleep(delay)

    if errors:
        _LOGGER.warning(
            "Received no complete response from %s: %s", ip_address, "; ".join(errors)
        )

    return data


async def send_command(
    hass: HomeAssistant,
    ip_address: str,
    base_url: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    port: int = DEFAULT_PORT,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
) -> bool:
    """Send a single command to the device.

    Returns True when the endpoint answered with a success status.
    """
    url = f"{base_url.format(ip=ip_address, port=port)}{endpoint.format(**(payload or {}))}"
    session = async_get_clientsession(hass)

    try:
        async with session.get(url, timeout=ClientTimeout(total=timeout)) as response:
            if response.status == 200:
                _LOGGER.debug("Command sent successfully to %s", url)
                return True

            _LOGGER.error("Command %s failed with HTTP %s", url, response.status)
            return False
    except (TimeoutError, ClientError) as err:
        _LOGGER.error("Command %s failed: %s", url, err)
        return False
