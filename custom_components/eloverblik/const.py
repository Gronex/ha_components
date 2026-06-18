"""Constants for the Eloverblik integration."""

DOMAIN = "eloverblik"

# Config entry keys
CONF_REFRESH_TOKEN = "refresh_token"
CONF_ENABLE_PRODUCTION = "enable_production"

# Metering point types (Eloverblik "typeOfMP" codes).
# Only E17/E18 are relevant for the Energy Dashboard as main meters.
METER_TYPE_CONSUMPTION = "E17"
METER_TYPE_PRODUCTION = "E18"

# Default polling interval. Energinet publishes data with ~1 day delay, so
# frequent polling adds no value; hourly keeps the "current period" sensor fresh
# while staying well within the API rate limits (120 req/min per IP).
DEFAULT_UPDATE_INTERVAL_SECONDS = 3600

# Aggregation used when fetching time series for statistics ingestion.
# "Hour" gives good resolution for the Energy Dashboard while keeping the
# per-request payload modest.
TIMESERIES_AGGREGATION = "Hour"

# How far back to fetch on the very first run (before any statistic exists)
# so the Energy Dashboard has some history right away. Keep within the API's
# 730-day per-request limit.
INITIAL_BACKFILL_DAYS = 30
