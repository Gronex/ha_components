"""Constants for the Eloverblik integration."""

DOMAIN = "eloverblik"

# Config entry keys
CONF_REFRESH_TOKEN = "refresh_token"
CONF_ENABLE_PRODUCTION = "enable_production"

# Metering point types (Eloverblik "typeOfMP" codes).
# Only E17/E18 are relevant for the Energy Dashboard as main meters.
METER_TYPE_CONSUMPTION = "E17"
METER_TYPE_PRODUCTION = "E18"

# Polling interval bounds, derived from each meter's reading occurrence
# (meter_reading_occurrence) and clamped to this range. Eloverblik publishes
# data with ~1 day delay regardless, so the 30-minute floor mainly catches
# delayed batches sooner; the 6-hour ceiling keeps slow meters from starving
# statistics. Well within the API rate limits (120 req/min per IP).
MIN_UPDATE_INTERVAL_SECONDS = 30 * 60
MAX_UPDATE_INTERVAL_SECONDS = 6 * 60 * 60

# Fallback interval used before the metering-point list is known (first tick)
# and when no meter's reading occurrence can be parsed.
DEFAULT_UPDATE_INTERVAL_SECONDS = 3600

# Aggregation used when fetching time series for statistics ingestion.
# "Hour" gives good resolution for the Energy Dashboard while keeping the
# per-request payload modest.
TIMESERIES_AGGREGATION = "Hour"

# How far back to fetch on the very first run (before any statistic exists)
# so the Energy Dashboard has some history right away. Keep within the API's
# 730-day per-request limit.
INITIAL_BACKFILL_DAYS = 30
