# A collection of documentation for the API's

- Hansgrohe Pontos REST API from:
https://community.home-assistant.io/t/hansgrohe-pontos-syr-safe-tech/576178

- Hansgrohe Pontos API found at:
https://community.symcon.de/t/hansgrohe-pontosbase/128469/6

- SYR API found at, translated to english:
https://iotsyrpublicapi.z1.web.core.windows.net/

> **Note (2.9.3):** the integration was renamed from `hass_pontos` to `pontos`. Service names in the
tables below are therefore `pontos.*`. See the [README](../README.md) for the upgrade steps.

# Integration features

## Sensors

The integration provides the following sensors in Home Assistant:

| Sensor Name                | Description                        | Unit      |
|----------------------------|------------------------------------|-----------|
| Total water consumption    | Total water used, never counts backwards | L    |
| Water pressure             | Current water pressure             | bar       |
| Water temperature          | Current water temperature          | °C        |
| Water flow                 | Current flow rate                  | L/h       |
| Current water consumption  | Current water draw                 | L         |
| Time since last turbine pulse | Time since last water flow      | s         |
| Leak test pressure drop    | Pressure drop during leak test     | bar       |
| Wifi state                 | WiFi connection status             |           |
| Wifi signal strength       | WiFi signal strength               | %         |
| Wifi SSID                  | Configured WLAN network            |           |
| Wifi networks              | Networks found by the device       |           |
| WLAN/LAN IP address, gateway | Current network configuration    |           |
| MAC address, MAC address LAN | MAC addresses of the interfaces  |           |
| Battery voltage            | Battery voltage                    | V         |
| Mains voltage              | Mains voltage                      | V         |
| Serial number              | Device serial number               |           |
| Code number                | Device code number (Pontos Base)   |           |
| Firmware version           | Device firmware version            |           |
| Hardware version           | Device hardware version            |           |
| Device type                | Device type                        |           |
| Alarm status               | Current alarm status, with the alarm history as attribute |  |
| Warning status             | Current warning status             |           |
| Notification status        | Current notification status        |           |
| Active profile             | Currently active profile           |           |
| Number of profiles         | Profiles reported by the device    |           |
| Valve status               | Current valve status               |           |
| Water conductivity         | Water conductivity                 | μS/cm     |
| Water hardness             | Water hardness                     | dH        |
| Raw water hardness         | Inlet water hardness               | °dH       |
| Treated water hardness     | Outlet water hardness              | °dH       |
| Salt quantity              | Remaining salt in the brine tank   | kg        |
| Salt stock                 | Remaining duration of salt         | weeks     |
| Regeneration status        | Current regeneration status        |           |
| Regeneration time remaining| Remaining regeneration time        | s         |
| Microleakage test interval | Microleakage test schedule         |           |
| Microleakage test status   | Status of the microleakage test    |           |
| Self-study determined volume/time/flow, remaining time | Results of the self-study phase | L, s, L/h |
| Profile 1-8 name           | Name of each profile               |           |

*Note: Available sensors may depend on your device model.*

## Binary sensors

| Binary sensor              | Description                                          |
|----------------------------|------------------------------------------------------|
| Leakage alarm              | On for leakage related alarms (volume, time, microleakage, external sensor) |
| Alarm active               | On while the device reports any alarm                |
| Warning active             | On while the device reports any warning              |
| Notification active        | On while the device reports any notification         |
| Wifi connected             | On while the WLAN connection is established          |
| Microleakage test active   | On while a microleakage test is running (SafeTech+)  |

## Numbers

For every profile the device reports, the following settings are available as `number` entities
(entity category *configuration*, they can be switched off with the *Create control entities*
option):

| Number entity              | Endpoint | Range     | Unit |
|----------------------------|----------|-----------|------|
| Profile n permitted volume | `PVn`    | 0-9000    | L    |
| Profile n permitted time   | `PTn`    | 0-1500    | min  |
| Profile n permitted flow   | `PFn`    | 0-5000    | L/h  |
| Profile n return time      | `PRn`    | 0-700     | h    |

## Services

The integration provides the following Home Assistant services. All of them accept a `device_id`
(or `entry_id`) to target a single device – without a target the command is sent to every
configured device.

| Service Name                | Fields                  | Description                                      |
|-----------------------------|-------------------------|--------------------------------------------------|
| `pontos.open_valve`         | –                       | Opens the water valve                            |
| `pontos.close_valve`        | –                       | Closes the water valve                           |
| `pontos.clear_alarms`       | –                       | Clears any active alarms                         |
| `pontos.clear_warnings`     | –                       | Clears any active warnings                       |
| `pontos.clear_notifications`| –                       | Clears any active notifications                  |
| `pontos.set_profile`        | `profile`               | Sets the active profile (1-8)                    |
| `pontos.set_profile_volume` | `profile`, `volume`     | Permitted volume of a profile in liters          |
| `pontos.set_profile_time`   | `profile`, `minutes`    | Permitted draw time of a profile                 |
| `pontos.set_profile_flow`   | `profile`, `flow`       | Permitted flow rate of a profile                 |
| `pontos.set_profile_return_time` | `profile`, `hours` | Return to the profile after n hours              |
| `pontos.set_profile_availability` | `profile`, `enabled` | Enables or disables a profile           |
| `pontos.set_profile_warning`| `profile`, `enabled`    | Leakage warning of a profile                     |
| `pontos.microleakage_test`  | –                       | Starts a microleakage test                       |
| `pontos.microleakage_time`  | `time`                  | Sets the time of the microleakage test (HH:MM)   |
| `pontos.microleakage_schedule` | `schedule`           | Sets the schedule (1 daily, 2 weekly, 3 monthly) |
| `pontos.start_self_study`   | `days`                  | Starts the self-study phase (0-28 days)          |
| `pontos.delete_self_study`  | –                       | Deletes the self-study values                    |
| `pontos.set_regeneration_mode` | `mode`               | Switches the NeoSoft regeneration mode           |
| `pontos.set_regeneration_interval` | `days`         | Days between NeoSoft regenerations               |
| `pontos.set_regeneration_time` | `time`               | Time of the NeoSoft regeneration                 |
| `pontos.enable_buzzer` / `pontos.disable_buzzer` | – | NeoSoft buzzer                    |
| `pontos.generic_service`    | `endpoint`, `data`      | Sends a custom command to the device             |

*Note: Available services may depend on your device model. The previous `data` field name is still
accepted for the services that take a single value.*

### Generic service call

The generic service call allows you to send commands to the device using the `/set` endpoints. This is useful for accessing features not covered by predefined services.

Example for changing profile to 1:
- Endpoint: prf
- Data: 1

Change maximum water draw for profile 2 to 250 l:
- Endpoint: pv2
- Data: 250

#### Commands Overview (Based on SYR documentation)

| **Endpoint** | **Type**       | **Description**                                      | **Value Range**       | **GET** | **SET** |
|-------------|----------------|------------------------------------------------------|------------------------|---------|---------|
| **AB**      | Bool           | Locking opening/closing                              | true/false            | ✓       | ✓       |
| **VLV**     | int            | Status of the shut-off                               | 10-21                 | ✓       | X       |
| **PAx**     | Bool           | Profile Availability                                 | true/false            | ✓       | ✓       |
| **PVx**     | int            | Profile permitted volume in liters                  | 0-9000                | ✓       | ✓       |
| **PTx**     | int            | Profile allowed time in minutes                     | 0-1500                | ✓       | ✓       |
| **PFx**     | int            | Profile permitted flow in l/h                       | 0-5000                | ✓       | ✓       |
| **PMx**     | Bool           | Micro leak test Activating/deactivating             | true/false            | ✓       | ✓       |
| **PWx**     | Bool           | Activation/deactivate leakage warning               | true/false            | ✓       | ✓       |
| **PBx**     | Bool           | Buzzer Activating/deactivating                      | true/false            | ✓       | ✓       |
| **PRx**     | int            | Return to Profile Present in hours                  | 0-700                 | ✓       | ✓       |
| **PRF**     | int            | Currently selected profile                          | 1-8                   | ✓       | ✓       |
| **DEX**     | Bool           | Starts the MicroLeakage Test                        | true                  | X       | ✓       |
| **DRP**     | int            | Set the test interval                               | 1-3                   | ✓       | ✓       |
| **DSV**     | int            | Status of the micro leakage                         | 0-3                   | ✓       | X       |
| **DTT**     | string         | Sets the time when the test is performed            | "HH:MM"               | ✓       | ✓       |
| **SLP**     | int            | Starts the self-study phase with duration in days   | 0-28                  | ✓       | ✓       |
| **SLV**     | int            | Determined volume in L during the self-study phase  | 0-9000                | ✓       | X       |
| **SLT**     | int            | Determined time in seconds during self-study phase  | 0-90000               | ✓       | X       |
| **SLF**     | int            | Determined flow rate in l/h during self-study phase | 0-5000                | ✓       | X       |
| **SLD**     | Bool           | Deletes the values when true is sent                | true                  | X       | ✓       |
| **SLE**     | int            | Remaining time in the active self-learning phase    | 0-2419200             | ✓       | X       |
| **WFC**     | string         | WLAN SSID                                           | true                  | ✓       | ✓       |
| **WFD**     | -              | SSID and Key Delete                                 | -                     | ✓       | ✓       |
| **WFK**     | string         | WiFi Key                                            | -                     | X       | ✓       |
| **WFL**     | json           | Provides a list of available networks              | -                     | ✓       | X       |
| **WFR**     | int            | WLAN signal strength in %                           | 1-100                 | ✓       | X       |
| **WFS**     | int            | WLAN connection status                              | 0-2                   | ✓       | X       |
| **WGW**     | string         | WLAN IP                                             | -                     | ✓       | X       |
| **WIP**     | string         | WLAN Gateway                                        | -                     | ✓       | X       |
| **EGW**     | string         | Ethernet IP                                         | -                     | ✓       | X       |
| **EIP**     | string         | Ethernet Gateway                                    | -                     | ✓       | X       |
| **MAC1**    | string         | MAC address WLAN interface                          | -                     | ✓       | X       |
| **MAC2**    | string         | MAC address LAN interface                           | -                     | ✓       | X       |
| **AVO**     | int            | Volume current removal in ml                        | -                     | ✓       | X       |
| **BAR**     | int            | Input pressure in mbar                              | 0-16000               | ✓       | X       |
| **BAT**     | int            | Battery voltage in 1/100 V                          | 0-1000                | ✓       | X       |
| **CEL**     | int            | Temperature in °C                                   | 0-1000                | ✓       | X       |
| **CND**     | int            | Conductance in uS/cm                                | 0-5000                | ✓       | X       |
| **FLO**     | int            | Current Flow rate in l/h                            | 0-5000                | ✓       | X       |
| **LTV**     | int            | Last tapped volume in liters                        | -                     | ✓       | X       |
| **NPS**     | int            | No turbine impulses since.. in s                   | -                     | ✓       | X       |
| **SRN**     | string         | Serial number of the device                         | -                     | ✓       | X       |
| **VER**     | string         | Firmware version of the device                      | -                     | ✓       | X       |
| **VOL**     | int            | Cumulative volume in liters                         | -                     | ✓       | X       |

### Endpoints used since 2.9.3

In addition to the endpoints above, the following endpoints are exposed as entities or services:

| Endpoint | Exposed as |
|---|---|
| `PA1`-`PA8` | `profile_enabled` attribute of the profile sensors, `pontos.set_profile_availability` |
| `PW1`-`PW8` | `leakage_warning_enabled` attribute, `pontos.set_profile_warning` |
| `PVn`/`PTn`/`PFn`/`PRn` | `number` entities plus `pontos.set_profile_volume/_time/_flow/_return_time` |
| `SLP`, `SLD` | `pontos.start_self_study`, `pontos.delete_self_study` |
| `SLV`, `SLT`, `SLF`, `SLE` | Self-study sensors (SafeTech+, Trio, SafeTech+ old firmware) |
| `PRN` | *Number of profiles* sensor, limits the profile entities that are created |
| `ALM` | `alarm_history` attribute of the *Alarm status* sensor |
| `WFC`, `WFL`, `WIP`, `WGW`, `EIP`, `EGW`, `MAC1`, `MAC2` | Diagnostic network sensors |
| `ALA`, `WRN`, `NOT`, `WFS`, `DSV` | Binary sensors (leakage alarm, alarm/warning/notification active, wifi connected, microleakage test active) |
| `CNO` | *Code number* diagnostic sensor (Pontos Base) |
