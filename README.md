# Pontos

[![GitHub Release](https://img.shields.io/github/release/acdcnow/pontos.svg?style=flat)](https://github.com/acdcnow/pontos/releases)
[![hassfest](https://img.shields.io/github/actions/workflow/status/acdcnow/pontos/hassfest.yaml?branch=master&label=hassfest)](https://github.com/acdcnow/pontos/actions/workflows/hassfest.yaml)
[![HACS](https://img.shields.io/github/actions/workflow/status/acdcnow/pontos/validate.yaml?branch=master&label=HACS)](https://github.com/acdcnow/pontos/actions/workflows/validate.yaml)

Home Assistant integration for **Hansgrohe Pontos** and **SYR** water meters, talking to the
device's local HTTP API on port 5333 – no cloud, no account, everything stays in your network.

> Fork of [sangvikh/hass-pontos](https://github.com/sangvikh/hass-pontos), maintained by
> [@acdcnow](https://github.com/acdcnow). All original work is by [@sangvikh](https://github.com/sangvikh).
> This fork is **not** the HACS default store repository: add it as a
> [custom repository](https://hacs.xyz/docs/faq/custom_repositories/) (see [Installation](#installation)).

## Features

* Water consumption, pressure, temperature, flow rate and conductivity sensors
* Water shut-off valve, profile selection, leak test and buzzer controls
* Binary sensors for leakage alarms, warnings, notifications and the WLAN state
* Profile settings (permitted volume, time, flow, return time, availability, leakage warning) as
  `number` entities and services
* Self-study phase of SYR SafeTech+/Trio devices (start, delete, determined values)
* Network diagnostics (SSID, available networks, WLAN/LAN IP and gateway, both MAC addresses)
* Configurable polling interval, HTTP timeout and retry behaviour
* Robust data handling: implausible values (for example a negative cumulative volume) never reach
  the recorder or the long term statistics
* All user visible text is available in English and German, French and Norwegian fall back to English

## Supported devices

| Device | Note |
|---|---|
| Hansgrohe Pontos Base | `http://<ip>:5333/pontos-base/` |
| SYR Trio | `http://<ip>:5333/trio/` |
| SYR SafeTech+ | `http://<ip>:5333/trio/` |
| SYR SafeTech+ (old firmware) | `http://<ip>:5333/safe-tec/` |
| SYR NeoSoft | `http://<ip>:5333/neosoft/` |

## Installation

### HACS (recommended)

1. Install [HACS](https://hacs.xyz/docs/configuration/basic/) if you have not already.
2. HACS → **⋮** → *Custom repositories* → add `https://github.com/acdcnow/pontos` with the
   category **Integration**.
3. Search for **Pontos** in HACS and install it.
4. Restart Home Assistant.
5. Add the integration: **Settings → Devices & Services → Add integration → Pontos**.

### Manual

1. Download or clone this repository.
2. Copy `custom_components/pontos` into your Home Assistant `custom_components` directory.
3. Restart Home Assistant.
4. Add the integration: **Settings → Devices & Services → Add integration → Pontos**.

### Upgrading from `hass-pontos` (2.9.2 or older)

The integration was renamed: the repository is now `acdcnow/pontos` and the integration domain
changed from `hass_pontos` to `pontos`. This requires one manual step, because Home Assistant can
only load one integration per folder:

1. In HACS, remove the old repository (`sangvikh/hass-pontos` or your previous fork).
2. Delete the folder `custom_components/hass_pontos` from your configuration directory.
3. Install this repository as a custom repository (see above) and restart Home Assistant.
4. Add the integration again: **Settings → Devices & Services → Add integration → Pontos**.

   The setup dialog detects the configuration of the previous version and offers to take it over.
   Confirm it, and your IP address, polling interval, device name and model are reused.

5. The old configuration entry and its entities are removed as part of the import. Because the
   devices and entities keep their names, the entity ids stay the same and your **history and
   long term statistics are preserved**.

## Configuration

During setup only the essentials are asked for; everything else can be changed later via
**Settings → Devices & Services → Pontos → Configure**.

| Field | Description |
|---|---|
| IP address | IP address of the device in your network |
| Port | HTTP port, default `5333` |
| Fetch interval | Polling interval in seconds (default 10) |
| Device name | Name of the device in Home Assistant |
| Device type | Model of your device, see [supported devices](#supported-devices) |

### Options

| Section | Option | Description |
|---|---|---|
| Connection | IP address, port | Where the device can be reached |
| Connection | HTTP timeout | Timeout per request in seconds |
| Connection | Retry attempts, retry delay | Retries per poll and the delay between them |
| Polling | Fetch interval | How often the device is polled |
| Device | Device name, device type | Rename the device or switch to another model |
| Data quality | Ignore implausible values | See [data quality](#data-quality) |
| Data quality | Keep last valid value for | How long the last valid value may be kept, `0` = unlimited |
| Data quality | Unit for volume sensors | Display volumes in `L` or `m³` |
| Entities | Create diagnostic entities | Turn the diagnostic sensors on or off |
| Entities | Create control entities | Turn buttons, selects, switches, times and numbers on or off |
| Logging | Enable debug logging | More verbose logging for this integration |

Saving the options reloads the config entry.

### Data quality

Water meters occasionally report values that cannot be correct: a device that is starting up, a
lost connection or an internal reset can produce a **negative cumulative volume** or a value that
does not parse as a number.

Such values are **ignored** by default:

* the sensor keeps its **last valid value**, so the dashboard and the statistics stay continuous,
* the rejected value is exposed in the entity attributes as `invalid_value` and `invalid_since`,
* the raw device value is always available as `raw_value`,
* if the device keeps sending implausible values for longer than *Keep last valid value for*
  (default 60 minutes), the sensor becomes `unavailable` instead of showing a stale value,
* after a restart the last known good value is restored, so a bogus first reading does not create a
  gap in the statistics.

Cumulative meters (state class `total_increasing`, for example *Total water consumption*) are
guarded automatically – a meter can never count backwards. If you really want the raw values, turn
*Ignore implausible values* off.

## Entities

The available entities depend on the model. The following table lists the most important ones:

| Entity | Type | Description |
|---|---|---|
| Total water consumption | sensor | Cumulative volume, `total_increasing` |
| Current water consumption | sensor | Volume of the current water draw |
| Water flow | sensor | Current flow rate in `L/h` |
| Water pressure | sensor | Input pressure |
| Water temperature | sensor | Water temperature |
| Water conductivity / Water hardness | sensor | Conductivity and calculated hardness |
| Alarm status, Warning status, Notification status | sensor | Current device state |
| Leakage alarm | binary sensor | `on` for leakage related alarms |
| Alarm / Warning / Notification active | binary sensor | `on` while the device reports an entry |
| WiFi connected | binary sensor | WLAN connection state |
| Water supply | valve | Open or close the shut-off valve |
| Profile | select | Active profile, by profile name |
| Profile *n* permitted volume / time / flow / return time | number | Profile limits, 1-8 |
| Microleakage test active | binary sensor | `on` while a leak test runs |
| Self-study *…* | sensor | Determined values of the self-study phase |
| Salt quantity, Salt stock | sensor | NeoSoft only |
| WLAN/LAN IP address, gateway, SSID, MAC | sensor | Diagnostic |

## Services

All services can target a single device with the **Device** field (or `entry_id`). Without a
target, the command is sent to **all** configured devices.

| Service | Fields | Description |
|---|---|---|
| `pontos.open_valve` / `pontos.close_valve` | – | Open or close the water valve |
| `pontos.clear_alarms` / `clear_warnings` / `clear_notifications` | – | Clear the respective list |
| `pontos.set_profile` | `profile` | Activate a profile (1-8) |
| `pontos.set_profile_volume` | `profile`, `volume` | Permitted volume in liters |
| `pontos.set_profile_time` | `profile`, `minutes` | Permitted draw time |
| `pontos.set_profile_flow` | `profile`, `flow` | Permitted flow in `L/h` |
| `pontos.set_profile_return_time` | `profile`, `hours` | Return to profile after n hours |
| `pontos.set_profile_availability` | `profile`, `enabled` | Enable/disable a profile |
| `pontos.set_profile_warning` | `profile`, `enabled` | Leakage warning of a profile |
| `pontos.microleakage_test` | – | Start a microleakage test |
| `pontos.microleakage_time` | `time` | Time of day of the leak test (`HH:MM`) |
| `pontos.microleakage_schedule` | `schedule` | `1` daily, `2` weekly, `3` monthly |
| `pontos.start_self_study` | `days` | Start the self-study phase (SafeTech+/Trio) |
| `pontos.delete_self_study` | – | Delete the determined self-study values |
| `pontos.set_regeneration_mode` | `mode` | NeoSoft regeneration mode |
| `pontos.set_regeneration_interval` | `days` | NeoSoft days between regenerations |
| `pontos.set_regeneration_time` | `time` | NeoSoft time of regeneration |
| `pontos.enable_buzzer` / `disable_buzzer` | – | NeoSoft buzzer |
| `pontos.generic_service` | `endpoint`, `data` | Send a raw command, see below |

### Generic service call

`pontos.generic_service` sends a command to any `/set` endpoint, which is useful for features that
are not covered by the entities above. The endpoint is given without the leading `set/`.

Example – change the permitted volume of profile 2 to 250 liters:

```yaml
action: pontos.generic_service
data:
  endpoint: pv2
  data: "250"
```

The commands documented for the SYR devices are listed in
[documentation/readme.md](documentation/readme.md).

## Troubleshooting

### The integration does not set up / `cannot_connect`

* Check that the device answers: `http://<ip>:5333/<prefix>/get/all` in a browser.
* Use the correct **device type** – the URL prefix differs per model (`pontos-base`, `trio`, `safe-tec`, `neosoft`).
* Make sure the port is not blocked and the device is in the same network.

### Some sensors show `unavailable`

* The device did not report a usable value yet, or the value was implausible and the tolerance ran out.
  Check the `raw_value` and `invalid_value` attributes of the entity.
* Diagnostic entities that the model does not support stay unavailable by design; you can switch them
  off with *Create diagnostic entities* or disable the individual entity.

### Statistics look wrong

* Leave *Ignore implausible values* enabled. A negative cumulative volume would otherwise be treated
  as a counter reset.
* If you changed *Unit for volume sensors*, the statistics continue in the new unit.

### Enable debug logging

```
logger:
  default: info
  logs:
    custom_components.pontos: debug
```

The *Enable debug logging* option does the same without editing `configuration.yaml`.

## Development

* `testing/serve.py` simulates the device endpoints, `testing/link_hass_pontos.sh` links this
  repository into a Home Assistant instance for development.
* `documentation/readme.md` documents the device API and all known endpoints.
* Pull requests must bump `version` in `custom_components/pontos/manifest.json` when the integration
  changes – the *Check Version* workflow enforces this.

## Credits

* Original integration by [@sangvikh](https://github.com/sangvikh) and contributors.
* Device documentation collected from the SYR API documentation and the Home Assistant community.
* Brand images by the [home-assistant/brands](https://github.com/home-assistant/brands) project.

## License

[MIT](LICENSE)
