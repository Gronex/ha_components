import asyncio
import logging
import os
from datetime import date, timedelta

from eloverblik.energinet.client import EnerginetClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    try:
        async with EnerginetClient(os.environ["EL_API_TOKEN"]) as client:
            metering_points = await client.async_get_metering_points()
            print("\n\nMetering points:\n")
            print(metering_points)

            res = await client.async_get_timeseries(
                from_date=date.today() + timedelta(days=-30),
                to_date=date.today(),
                aggregation="Actual",
                metering_points=[point.metering_point_id for point in metering_points],
            )
            print("\n\nTime series:\n")
            print(res)
    except BaseException:
        logger.exception("Unhandled exception from Energinet client")


if __name__ == "__main__":
    asyncio.run(main())
