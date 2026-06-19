# AGENTS.md

High-signal context for working in this repo. Read before editing.

## What this is

A Home Assistant **custom integration** (`custom_components/eloverblik/`) for the
Danish Eloverblik / Energinet customer electricity API. Distributed via HACS.
The integration runs *inside* Home Assistant, not as a standalone app.

- Requires **Python 3.14+** and **Home Assistant 2026.6.0+** (see `pyproject.toml`, `hacs.json`).
- `httpx` and `pydantic` are shipped by HA — they are listed in `pyproject.toml`
  only to satisfy the standalone dev harness (`main.py`) and local tooling. **Do
  not add runtime dependencies** for the integration itself; anything not in
  `manifest.json`'s `dependencies` is unavailable at runtime in HA.

## Dev commands

```bash
uv sync                                # install deps into .venv
uv run --env-file .env main.py         # standalone client smoke test (needs EL_API_TOKEN in .env)
uv run ruff check custom_components main.py   # lint
uvx basedpyright                       # typecheck (config in pyrightconfig.json)
```

Notes an agent would otherwise get wrong:

- **There is no test suite.** Do not invent `pytest`, `tox`, or test-file patterns.
- The typechecker is **basedpyright** (not pyright). It is invoked via `uvx`,
  not through the project venv.
- `main.py` is a **dev harness**, not part of the integration. Never import
  integration logic through it.
- Lint/typecheck scope is `custom_components` + `main.py` (see `pyrightconfig.json`).
- Required verification order after changes: **lint → typecheck**. There is no
  `test` step.

## Architecture

```
custom_components/eloverblik/
  __init__.py        async_setup_entry; forwards Platform.SENSOR
  manifest.json      HA manifest; depends on ["recorder"] for statistics
  const.py           DOMAIN, config keys, polling interval, meter type codes
  config_flow.py     UI setup + reauth; validates refresh token by listing meters
  coordinator.py     EloverblikCoordinator — fetch + statistics ingestion (the core)
  sensor.py          one energy sensor per metering point
  icons.json, strings.json, translations/en.json   UI strings (en only)
  energinet/
    client.py        EnerginetClient (httpx async) for api.eloverblik.dk
    models.py        pydantic v2 models; many fields use camelCase aliases
```

External references:

- **Eloverblik customer API docs**:
  https://docs.eloverblik.dk/en/docs/api/customer#description/introduction
  Authoritative source for endpoints, auth flow, and payload shapes. Consult it
  before changing `energinet/client.py` or `energinet/models.py`.

Key execution flow:

- `EloverblikCoordinator` is a `DataUpdateCoordinator` that polls hourly
  (`DEFAULT_UPDATE_INTERVAL_SECONDS = 3600`). It fetches metering points + time
  series and **inserts historical data into HA statistics** via
  `async_add_external_statistics`. Sensors read the latest cumulative sum from
  the coordinator payload; long-term history comes from statistics, not state.
- Statistics IDs follow `eloverblik:<metering_point_id>_consumption` /
  `_production`. Initial backfill is 30 days (`INITIAL_BACKFILL_DAYS`); after
  that, fetches resume from the last recorded statistic.
- Only **E17** (consumption) and **E18** (production) meter types are exposed.
  Production meters are **off by default** (`CONF_ENABLE_PRODUCTION`).

## Conventions and gotchas

- **Auth model**: a refresh token is exchanged for a short-lived bearer token
  (`/customerapi/api/token`); the client transparently refreshes on HTTP 401
  (`_execute_with_auth` in `energinet/client.py`). Inside the coordinator,
  auth failures surface as `_AuthError` and are translated to
  `ConfigEntryAuthFailed` to trigger HA's reauth flow. When extending the
  client, reuse `_execute_with_auth`; do not hand-roll auth headers.
- **Don't remove the `# type: ignore[reportIncompatibleVariableOverride]` on
  `EloverblikSensor`** (`sensor.py`). It works around an HA base-class MRO
  conflict on `available` (`property` vs `cached_property`) that exists in HA
  itself; same pattern as the built-in `opower` integration.
- **`reportUnusedCallResult` is disabled** in `pyrightconfig.json`. The
  intentional `self._client = await client.__aenter__()` assignment in
  `client.py` relies on this — do not "clean it up".
- `pyrightconfig.json` deliberately relaxes many strictness checks
  (`reportAny`, `reportUnknown*`, etc.). Match existing style; don't tighten
  globally without reason.
- Entity naming uses `translation_key` (`energy_consumption` /
  `energy_production`) resolved via `strings.json` / `translations/en.json`.
  Only `en` is shipped.
- Models use pydantic v2 with camelCase aliases via `to_camel` and explicit
  `validation_alias` / `serialization_alias` for non-standard fields (e.g.
  `typeOfMP`, `mRID`, `MarketEvaluationPoint`). Preserve aliasing when adding
  fields.
- The dummy listener added in `EloverblikCoordinator.__init__` is intentional:
  it keeps the coordinator ticking even before sensors attach, so statistics
  get backfilled. Do not remove it.
