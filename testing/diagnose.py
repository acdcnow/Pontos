#!/usr/bin/env python3
"""Probe a Pontos / SYR water meter and report what it answers.

This script talks to the device exactly like the integration does, but without
Home Assistant, so it separates "the device or the network is the problem" from
"the integration is the problem". It only uses the standard library.

Usage:
    python3 diagnose.py 192.168.1.100
    python3 diagnose.py pontos.fritz.box --port 5333
    python3 diagnose.py 192.168.1.100 --make "SYR SafeTech+"

Without --make every known device family is tried, and the script reports which
URL prefix answers. Exit code 0 means at least one endpoint returned data.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request

#: Device family -> (URL prefix, endpoints the integration requests).
#: Kept in sync with custom_components/pontos/device_config/conf_*.py.
DEVICES: dict[str, tuple[str, tuple[str, ...]]] = {
    "Hansgrohe Pontos": ("pontos-base", ("set/ADM/(2)f", "get/cnd", "get/all")),
    "SYR Trio": ("trio", ("get/all",)),
    "SYR SafeTech+": ("trio", ("get/all",)),
    "SYR SafeTech+ (Old firmware)": ("safe-tec", ("set/ADM/(2)f", "get/all")),
    "SYR NeoSoft": ("neosoft", ("get/all",)),
}

BODY_PREVIEW = 200


def describe_body(body: str) -> str:
    """Return a short description of an HTTP body."""
    text = body.strip()
    if not text:
        return "<empty body>"

    try:
        payload = json.loads(text)
    except ValueError:
        return f"not JSON: {text[:BODY_PREVIEW]!r}"

    if isinstance(payload, dict):
        keys = sorted(payload)
        sample = ", ".join(f"{key}={payload[key]!r}" for key in keys[:6])
        return f"JSON object, {len(keys)} keys: {sample}"
    return f"JSON {type(payload).__name__}: {text[:BODY_PREVIEW]!r}"


def fetch(url: str, timeout: float) -> tuple[bool, str]:
    """Fetch a URL and return (ok, description)."""
    request = urllib.request.Request(url, headers={"User-Agent": "pontos-diagnose"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            elapsed = time.monotonic() - started
            content_type = response.headers.get("Content-Type", "<none>")
            print(
                f"     HTTP {response.status} in {elapsed:.2f}s,"
                f" Content-Type: {content_type}, {len(body)} bytes"
            )
            print(f"     {describe_body(body)}")
            return response.status == 200, body
    except urllib.error.HTTPError as err:
        print(f"     HTTP {err.code} {err.reason}")
        return False, ""
    except urllib.error.URLError as err:
        print(f"     connection failed: {err.reason}")
        return False, ""
    except (TimeoutError, socket.timeout):
        print(f"     timed out after {timeout}s")
        return False, ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="IP address or host name of the device")
    parser.add_argument(
        "--port", type=int, default=5333, help="TCP port (default 5333)"
    )
    parser.add_argument("--timeout", type=float, default=5.0, help="timeout in seconds")
    parser.add_argument(
        "--make",
        choices=list(DEVICES),
        help="only probe this device family instead of all of them",
    )
    args = parser.parse_args()

    print(f"Host: {args.host}  Port: {args.port}  Timeout: {args.timeout}s")

    try:
        print(f"Resolves to: {socket.gethostbyname(args.host)}")
    except OSError as err:
        print(f"Name resolution failed: {err}")
        print("-> Use the IP address of the device if the name does not resolve.")
        return 2

    families = [args.make] if args.make else list(DEVICES)
    working: list[str] = []

    for make in families:
        prefix, endpoints = DEVICES[make]
        print()
        print(f"--- {make}: /{prefix}/ ---")
        answered = 0
        for endpoint in endpoints:
            url = f"http://{args.host}:{args.port}/{prefix}/{endpoint}"
            print(f"  GET {url}")
            ok, _body = fetch(url, args.timeout)
            answered += bool(ok)
            time.sleep(0.2)

        if answered:
            working.append(make)
            print(f"  -> {answered}/{len(endpoints)} endpoint(s) answered")

    print()
    if working:
        print(f"RESULT: the device answers as: {', '.join(working)}")
        print("Select that device type in the integration. If the integration still")
        print("shows no entities, enable debug logging and check the warning from")
        print("'Received no complete response from ...'.")
        return 0

    print("RESULT: none of the endpoints answered.")
    print("Check that the device is powered, on the same network and that the port")
    print(
        f"({args.port}) is reachable - e.g. 'http://{args.host}:{args.port}/' in a browser."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
