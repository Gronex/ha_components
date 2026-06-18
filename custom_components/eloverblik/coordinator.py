"""DataUpdateCoordinator for the Eloverblik integration.

Fetches metering points and time series from the Energinet customer API and
inserts the (delayed) historical data into Home Assistant statistics so it can
be consumed by the Energy dashboard. Also exposes the latest value per meter as
the state of a live sensor entity.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
import re
from typing import override

import httpx

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.recorder import get_instance
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import EnergyConverter

from .const import (
    CONF_ENABLE_PRODUCTION,
    CONF_REFRESH_TOKEN,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    INITIAL_BACKFILL_DAYS,
    METER_TYPE_CONSUMPTION,
    METER_TYPE_PRODUCTION,
    TIMESERIES_AGGREGATION,
    DOMAIN,
)
from .energinet.client import EnerginetClient
from .energinet.models import MeteringPoint, ResponseItem

_LOGGER = logging.getLogger(__name__)

type EloverblikConfigEntry = ConfigEntry["EloverblikCoordinator"]


@dataclass
class MeterData:
    """Latest state for a single metering point, exposed to sensor entities."""

    metering_point_id: str
    is_production: bool
    name: str
    latest_sum: float | None
    latest_start: datetime | None


@dataclass
class EloverblikData:
    """Aggregated coordinator payload."""

    meters: dict[str, MeterData]


_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def _resolution_to_timedelta(resolution: str | None) -> timedelta:
    """Parse an ISO 8601 duration (e.g. PT1H, PT15M, P1D) into a timedelta."""
    if not resolution:
        return timedelta(hours=1)
    if match := _DURATION_RE.match(resolution):
        parts = {k: int(v) for k, v in match.groupdict(default="0").items()}
        return timedelta(
            days=parts["days"],
            hours=parts["hours"],
            minutes=parts["minutes"],
            seconds=parts["seconds"],
        )
    _LOGGER.warning(
        "Unrecognized time series resolution %r, defaulting to 1h", resolution
    )
    return timedelta(hours=1)


class EloverblikCoordinator(DataUpdateCoordinator[EloverblikData]):
    """Handle fetching Eloverblik data and inserting statistics."""

    config_entry: EloverblikConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: EloverblikConfigEntry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="Eloverblik",
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL_SECONDS),
        )
        self._client = EnerginetClient(config_entry.data[CONF_REFRESH_TOKEN])
        self._metering_points: list[MeteringPoint] | None = None

        # Keep the coordinator ticking even when no sensor listeners are
        # attached yet, so statistics still get backfilled. Mirrors the opower
        # integration approach.
        @callback
        def _dummy_listener() -> None:
            pass

        self.async_add_listener(_dummy_listener)

    @property
    def client(self) -> EnerginetClient:
        """Return the underlying API client."""
        return self._client

    @override
    async def _async_update_data(self) -> EloverblikData:
        """Fetch data from the API and update statistics."""
        try:
            await self._client.open()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Error opening Eloverblik client: {err}") from err

        if self._metering_points is None:
            try:
                self._metering_points = await self._fetch_metering_points()
            except _AuthError as err:
                raise ConfigEntryAuthFailed from err
            except httpx.HTTPError as err:
                raise UpdateFailed(
                    f"Error communicating with Eloverblik: {err}"
                ) from err

        enable_production = bool(
            self.config_entry.data.get(CONF_ENABLE_PRODUCTION, False)
        )
        relevant: list[MeteringPoint] = []
        for mp in self._metering_points:
            if mp.type_of_mp == METER_TYPE_CONSUMPTION:
                relevant.append(mp)
            elif mp.type_of_mp == METER_TYPE_PRODUCTION and enable_production:
                relevant.append(mp)

        meters: dict[str, MeterData] = {}
        for mp in relevant:
            is_production = mp.type_of_mp == METER_TYPE_PRODUCTION
            try:
                latest_sum, latest_start = await self._update_statistics(
                    mp, is_production
                )
            except _AuthError as err:
                raise ConfigEntryAuthFailed from err
            meters[mp.metering_point_id] = MeterData(
                metering_point_id=mp.metering_point_id,
                is_production=is_production,
                name=_meter_name(mp),
                latest_sum=latest_sum,
                latest_start=latest_start,
            )

        return EloverblikData(meters=meters)

    async def _fetch_metering_points(self) -> list[MeteringPoint]:
        """Fetch metering points, translating auth issues into a typed error."""
        try:
            points = await self._client.async_get_metering_points()
        except RuntimeError as err:
            if "Authentication" in str(err):
                raise _AuthError from err
            raise
        return points

    async def _update_statistics(
        self, metering_point: MeteringPoint, is_production: bool
    ) -> tuple[float | None, datetime | None]:
        """Insert time series for one metering point into statistics.

        Returns the latest cumulative sum and its period start time.
        """
        suffix = "production" if is_production else "consumption"
        statistic_id = f"{DOMAIN}:{metering_point.metering_point_id}_{suffix}"
        name = f"Eloverblik {metering_point.metering_point_id} {suffix}"

        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=name,
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_class=EnergyConverter.UNIT_CLASS,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

        last_stat = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, True, {"sum"}
        )

        if last_stat and last_stat.get(statistic_id):
            last_row = last_stat[statistic_id][0]
            running_sum = float(last_row.get("sum") or 0.0)
            last_start_ts = last_row.get("start")
            from_date = (
                dt_util.utc_from_timestamp(last_start_ts).date()
                if last_start_ts is not None
                else dt_util.utcnow().date() - timedelta(days=INITIAL_BACKFILL_DAYS)
            )
        else:
            running_sum = 0.0
            last_start_ts = None
            from_date = dt_util.utcnow().date() - timedelta(days=INITIAL_BACKFILL_DAYS)

        to_date = dt_util.utcnow().date()
        if from_date >= to_date:
            # Nothing new to fetch; report the last known sum if any.
            if last_stat and last_stat.get(statistic_id):
                row = last_stat[statistic_id][0]
                ts = row.get("start")
                return running_sum, (
                    dt_util.utc_from_timestamp(ts) if ts is not None else None
                )
            return None, None

        items = await self._fetch_timeseries(
            metering_point.metering_point_id, from_date, to_date
        )
        points = _flatten_points(items, metering_point.metering_point_id)

        statistics: list[StatisticData] = []
        latest_sum: float | None = None
        latest_start: datetime | None = None

        for start, quantity in points:
            # Skip anything at or before the last recorded point to avoid dupes.
            if last_stat and last_stat.get(statistic_id):
                if last_start_ts is not None and start.timestamp() <= last_start_ts:
                    continue
            value = max(0.0, quantity)
            running_sum += value
            statistics.append(StatisticData(start=start, state=value, sum=running_sum))
            latest_sum = running_sum
            latest_start = start

        if statistics:
            _LOGGER.debug(
                "Inserting %d statistic points for %s", len(statistics), statistic_id
            )
            async_add_external_statistics(self.hass, metadata, statistics)
        elif latest_sum is None and last_stat and last_stat.get(statistic_id):
            # Carry forward the last known values when nothing new arrived.
            row = last_stat[statistic_id][0]
            ts = row.get("start")
            latest_sum = float(row.get("sum") or 0.0)
            latest_start = dt_util.utc_from_timestamp(ts) if ts is not None else None

        return latest_sum, latest_start

    async def _fetch_timeseries(
        self, metering_point_id: str, from_date: date, to_date: date
    ) -> list[ResponseItem]:
        """Fetch time series for a single metering point, mapping auth errors."""
        try:
            return await self._client.async_get_timeseries(
                from_date=from_date,
                to_date=to_date,
                aggregation=TIMESERIES_AGGREGATION,
                metering_points=[metering_point_id],
            )
        except RuntimeError as err:
            if "Authentication" in str(err):
                raise _AuthError from err
            raise
        except httpx.HTTPError as err:
            raise UpdateFailed(
                f"Error fetching time series for {metering_point_id}: {err}"
            ) from err

    async def async_ws_close(self) -> None:
        """Close the underlying API client (called on unload)."""
        await self._client.close()


def _flatten_points(
    items: list[ResponseItem], metering_point_id: str
) -> list[tuple[datetime, float]]:
    """Flatten a time series response into (start_utc, kwh) tuples."""
    result: list[tuple[datetime, float]] = []
    for item in items:
        if not item.success:
            _LOGGER.debug(
                "Unsuccessful timeseries item for %s: %s",
                metering_point_id,
                item.error_text,
            )
            continue
        doc = item.market_document
        if doc is None or not doc.time_series:
            continue
        for series in doc.time_series:
            if series.periods is None:
                continue
            for period in series.periods:
                if period.time_interval is None or period.time_interval.start is None:
                    continue
                period_start = period.time_interval.start
                step = _resolution_to_timedelta(period.resolution)
                points = period.points or []
                for point in points:
                    position = int(point.position) if point.position else 1
                    quantity = float(point.quantity) if point.quantity else 0.0
                    start = period_start + (position - 1) * step
                    result.append((start, quantity))
    result.sort(key=lambda pair: pair[0])
    return result


def _meter_name(metering_point: MeteringPoint) -> str:
    """Build a human-friendly name for a metering point."""
    parts = [metering_point.first_consumer_party_name]
    if metering_point.city_name:
        parts.append(metering_point.city_name)
    name = ", ".join(p for p in parts if p)
    return name or metering_point.metering_point_id


class _AuthError(Exception):
    """Internal sentinel for authentication failures raised by the client."""
