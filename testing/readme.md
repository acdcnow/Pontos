# Testing

Simulates the endpoints used in the integration, making it possible to test device implementation without having a device available.

## How to use

Run with python from terminal, specify which sensor to simulate using '--device='. You can also specify the port and host IP address using the `--port` and `--host` arguments. Default is 0.0.0.0 port 5333
````
python3 serve.py --device safetech
python3 serve.py --device pontos
python3 serve.py --device safetech_v4
python3 serve.py --device neosoft
````

## Hardlinking into home assistant
Needs to be done on git pull/reset etc. Allows for editing files in the git repository and have it update within home assistant automatically.

````
bash link_pontos.sh
````

`link_hass_pontos.sh` does the same and is kept for the pre-2.9.3 name.

## Diagnosing a device

`diagnose.py` talks to a real device without Home Assistant and prints what it answers. Use it when
the integration reports *cannot connect* or shows no entities, and to find out which device type a
meter is:

````
python3 diagnose.py 192.168.1.100
python3 diagnose.py pontos.fritz.box --port 5333 --make "SYR SafeTech+"
````

It only uses the standard library, so it runs on any machine (including the Home Assistant host).

## Offline smoke test

`offline_smoke.py` runs the real integration code without Home Assistant. It stubs the Home Assistant
imports, feeds the payload of every `*.json` fixture through the coordinator and then executes
`async_setup_entry`, the platform setups, the entity properties, every service of the device type and
`async_unload_entry`:

````
python3 offline_smoke.py
python3 offline_smoke.py --make "SYR NeoSoft"
````

Use it after changing the integration. It catches the errors that only appear at runtime - a wrong
container type, a signature mismatch between a service schema and its endpoint, a deadlock between the
poller and the command lock, a Python boolean in a URL - none of which a linter or `hassfest` can see.
Exit code 0 means every device type sets up, creates its entities, answers its services and unloads.

## Endpoint coverage

`endpoint_matrix.py` compares the keys of every simulated device payload with the endpoints that are
referenced in the device configurations. Run it with plain python to see which endpoints of a
fixture are not used yet:

````
python endpoint_matrix.py
````
