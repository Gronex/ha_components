# Eloverblik (Energinet)

A [Home Assistant](https://www.home-assistant.io/) custom integration that pulls
your electricity data from the Danish **Eloverblik / Energinet** customer API and
feeds it into Home Assistant, with first-class support for the **Energy
Dashboard**.

Consumption data from Energinet is published on a per-meter reading schedule,
so this integration inserts the historical time series into Home Assistant
**statistics** (which survive restarts and backfill the past) and also exposes
live energy sensors. This makes the data usable in the Energy Dashboard's
*Grid consumption* (and optionally *Return to grid*) columns.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![hatch](https://img.shields.io/badge/Home%20Assistant-2026.6.0%2B-18BCF2.svg)](https://www.home-assistant.io/)

[![Add repository to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Gronex&repository=ha_components)
[![Add integration](https://my.home-assistant.io/badges/config_flow.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=eloverblik)

## Features

- **Config flow** setup — enter your Eloverblik refresh token in the UI.
- **Energy Dashboard ready** — per-metering-point `energy` sensors
  (`device_class: energy`, `state_class: total_increasing`, `kWh`) that you can
  add directly to the Energy Dashboard.
- **Long-term statistics** — delayed historical data is backfilled into
  statistics (`eloverblik:<metering_point_id>_consumption` / `_production`) so
  history is preserved across restarts.
- **Consumption (E17)** meters by default; **production (E18)** meters optional
  and **off by default** — enable it only if you have solar/production.
- **Automatic re-authentication** flow when the refresh token expires.
- Hourly polling, well within Eloverblik's rate limits.

## Prerequisites

1. A refresh token from
   [eloverblik.dk](https://eloverblik.dk): **Mit Eloverblik → Data → Adgang til data → Opret refresh token**.
2. The metering points you want to read must have a **relation** to your account
   (managed in the Eloverblik portal).

## Installation

### Option A — HACS (recommended)

1. Install [HACS](https://hacs.xyz) if you haven't already.
2. Click the *Add repository to HACS* button above, or in Home Assistant go to
   **HACS → Integrations → ⋮ → Custom repositories**, paste
   `https://github.com/Gronex/ha_components`, and set the category to
   **Integration**.
3. Search for **Eloverblik** in HACS and click **Download**.
4. Restart Home Assistant.

> Using a private fork? Generate a GitHub Personal Access Token with `repo`
> (classic) or *Contents: Read* on the repo (fine-grained), and add it under
> **HACS → ⚙️ Configuration**. HACS then reads private custom repositories with
> that token.

### Option B — Manual (HAOS)

1. Install the **Samba share** or **SSH & Web Terminal** add-on.
2. Copy the `custom_components/eloverblik/` folder into
   `/config/custom_components/` on your Home Assistant instance.
3. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add integration**.
2. Search for **Eloverblik**.
3. Paste your **refresh token**.
4. Leave **Enable production meters** off unless you have production (solar)
   metering points.

If the token is rejected, the integration will prompt you to re-authenticate.

## Energy Dashboard setup

After setup, add the generated sensor(s) to the Energy Dashboard
(**Settings → Dashboards → Energy**). Each metering point is exposed as a
device named after its grid company and city (e.g. *"<grid company>, <city>"*)
with a single **Consumption** (E17) or **Production** (E18) energy sensor.
Entity IDs are derived from the device name, so pick the sensor from the
device in the picker rather than searching for a hard-coded ID:

- **Grid consumption** → the *Consumption* sensor on each E17 meter's device.
- **Return to grid** → the *Production* sensor on each E18 meter's device, if
  you enabled production.

Long-term history also exists as external statistics under
`eloverblik:<metering_point_id>_consumption` and
`eloverblik:<metering_point_id>_production`, which you can select directly in
the Energy Dashboard.

## Entities

Each metering point creates one device (named *"<grid company>, <city>"*) with
a single energy sensor. Entity IDs are derived from the device name and the
translated entity name (e.g. `sensor.<grid_company>_<city>_consumption`); the
metering-point ID is stored as the device serial number and the sensor's unique
ID (`<metering_point_id>_energy`).

| Entity (on the device)   | Class   | State class       | Unit |
| ------------------------ | ------- | ----------------- | ---- |
| Consumption / Production | Energy  | Total increasing  | kWh  |

## Limitations

- **Delayed data** — freshness depends on each metering point's reading
  occurrence (reported by Eloverblik). The live sensor reflects the most
  recent *available* reading.
- **API rate limits** — 120 requests/min/IP and a 730-day maximum per request
  (enforced by Energinet). The integration polls hourly and fetches at most 30
  days at a time after the initial backfill.
- Only **E17** (consumption) and **E18** (production) metering points are
  exposed.

## Development

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run --env-file .env main.py     # standalone client smoke test (needs EL_API_TOKEN)
uv run ruff check custom_components main.py
uvx basedpyright                   # config in pyrightconfig.json
```

The integration source lives under `custom_components/eloverblik/`; the
underlying Energinet API client is in `custom_components/eloverblik/energinet/`.

[Eloverblik customer API documentation](https://docs.eloverblik.dk/en/docs/api/customer#description/introduction)
