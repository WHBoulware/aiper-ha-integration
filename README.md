# Aiper Pool Cleaner — Home Assistant custom integration

Unofficial, reverse-engineered integration for Aiper cordless pool robots
(Scuba / Surfer X9, X30, N30/N31, B30, S1/S2, T1, X5/X6/X7, W2, and the RM01
irrigation robot). It signs in to your Aiper cloud account, discovers your
devices, and exposes battery, online state and work status in Home Assistant,
with a vacuum entity for control.

> **Status:** status read-out works out of the box. Control (start/stop/recall)
> needs one ~20-minute traffic capture to lock in the device's binary command
> frames — see `tools/capture_guide.md`. This is unavoidable: the app sends
> commands as a protobuf/binary frame that isn't present in the app's text, so
> it has to be observed once rather than guessed. Everything else is wired and
> waiting for that table.

Not affiliated with or endorsed by Aiper. For use with hardware you own.

## Install

1. Copy `custom_components/aiper/` into your HA `config/custom_components/`
   directory (or add this repo to HACS as a custom integration).
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → "Aiper Pool Cleaner"**.
4. Enter your Aiper app email + password and pick the **region** your account
   was created in (America / Europe / Asia).

Requirements (installed automatically from `manifest.json`):
`pycryptodome` (request crypto) and `awsiotsdk` (live MQTT; optional — the
integration falls back to cloud polling if it can't connect).

## What you get

- **Vacuum** entity per robot — battery, activity state, and Start / Stop /
  Pause / Return buttons (buttons active once the command table is filled in).
- **Sensors** — battery %, work status, error code, firmware.
- **Binary sensor** — online/connectivity.

Polling interval and whether to use MQTT are in the integration's **Options**.

## Layout

```
custom_components/aiper/
  const.py        endpoints, hosts, topics, embedded RSA public key
  crypto.py       AES+RSA request envelope (self-tested round-trip)
  api.py          REST client: login, refresh, discover, status
  mqtt.py         AWS IoT MQTT: live state + command publish (build_command = the one TODO)
  coordinator.py  polling + live-state merge
  vacuum.py / sensor.py / binary_sensor.py / entity.py
PROTOCOL.md       full reverse-engineering notes (what's confirmed vs. needs capture)
tools/capture_guide.md   how to finish control with mitmproxy
```

## Finishing control

Open `tools/capture_guide.md`. In short: run mitmproxy, press Start/Stop/Recall
in the real app once each, paste the captured bytes into `mqtt.build_command`,
restart HA. If login itself is rejected, the same guide lists the four AES
settings to try in `crypto.py` (default is CBC + zero IV).

## Caveats

- Reverse-engineered and unofficial; Aiper can change the API at any time.
- Field names and the `workStatus` number→state mapping are best-effort from
  the binary; adjust `const.py`/`vacuum.py` if your model reports differently.
- Keep your account credentials in HA only; nothing here phones anywhere but
  Aiper's own regional API and AWS IoT endpoint.
