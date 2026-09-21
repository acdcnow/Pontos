# Hansgrohe Pontos

Local integration for **Hansgrohe Pontos** and **SYR** water meters (Trio, SafeTech+, SafeTech+ old
firmware, NeoSoft). Everything is polled directly from the device over your local network – no
cloud, no account. In Home Assistant the integration is listed as **Hansgrohe Pontos**, the domain
stays `pontos`.

## What you get

* **Sensors** – water consumption (cumulative and current), flow rate, pressure, temperature,
  conductivity and water hardness, plus diagnostics for WLAN, battery, mains and firmware.
* **Binary sensors** – leakage alarm, active alarm/warning/notification, WLAN state and running
  microleakage test.
* **Controls** – water shut-off valve, profile selection, microleakage test, buzzer and the
  profile limits (volume, time, flow, return time, availability, leakage warning) as editable
  numbers, 1-8 profiles depending on your device.
* **Self-study phase** for SYR SafeTech+/Trio – start it, delete it and read the determined values.
* **Reliable statistics** – implausible values such as a negative cumulative volume are ignored, the
  last valid value is kept and the rejected value is exposed as an attribute.
* **A tidy device list** – every meter gets a second device for its settings (profile limits,
  microleakage schedule, regeneration, buzzer), linked to the meter as a sub device.

## Configuration

IP address, port and polling interval are set during setup. Device name and model, HTTP timeout,
retries, data quality behaviour (including the display unit `L` or `m³`), whether diagnostic and
control entities are created, and debug logging can all be changed later in the integration's
options – saving the options reloads the device.

## Services

`open_valve`, `close_valve`, `clear_alarms`, `clear_warnings`, `clear_notifications`, `set_profile`,
`set_profile_volume`, `set_profile_time`, `set_profile_flow`, `set_profile_return_time`,
`set_profile_availability`, `set_profile_warning`, `microleakage_test`, `microleakage_time`,
`microleakage_schedule`, `start_self_study`, `delete_self_study`, `set_regeneration_mode`,
`set_regeneration_interval`, `set_regeneration_time`, `enable_buzzer`, `disable_buzzer` and
`generic_service` for raw device commands.

All services can target a single device, otherwise the command is sent to every configured device.

## Upgrading

Coming from `hass_pontos` (2.9.2 or older)? Remove the old integration folder, install this
repository and add the integration again – the setup dialog imports your existing configuration
automatically. See the
[README](https://github.com/acdcnow/pontos#upgrading-from-hass-pontos-292-or-older) for the details.
