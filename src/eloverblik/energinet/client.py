import logging
from datetime import date
from types import TracebackType
from typing import Awaitable, Callable, Literal

import httpx

from eloverblik.energinet.models import EnergyDataResponse, MeteringPoint, ResponseItem

logger = logging.getLogger(__name__)

Aggregation = Literal["Actual", "Quarter", "Hour", "Day", "Month", "Year"]


class EnerginetClient:
    __token: str | None
    __client: httpx.AsyncClient
    __refresh_token: str

    def __init__(self, refresh_token: str):
        self.__token = None
        self.__refresh_token = refresh_token

    async def __aenter__(self):
        self.__client = httpx.AsyncClient(
            base_url="https://api.eloverblik.dk", timeout=60
        )
        await self.__client.__aenter__()
        return self

    async def async_get_timeseries(
        self,
        from_date: date,
        to_date: date,
        aggregation: Aggregation,
        metering_points: list[str],
    ) -> list[ResponseItem]:
        response = await self.__async_execute_with_auth(
            lambda: self.__client.post(
                f"/customerapi/api/meterdata/gettimeseries/{from_date}/{to_date}/{aggregation}",
                headers={
                    "api-version": "1.0",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.__token}",
                },
                json={"meteringPoints": {"meteringPoint": metering_points}},
            )
        )

        if response.is_error:
            logger.error(
                "Failed to get time series",
                extra={
                    "from_date": from_date,
                    "to_date": to_date,
                    "aggregation": aggregation,
                    "metering_points": metering_points,
                    "code": response.status_code,
                    "reason": response.reason_phrase,
                    "response": response.text,
                },
            )
            return []

        return EnergyDataResponse.model_validate(response.json()["result"]).root

    async def async_get_metering_points(self) -> list[MeteringPoint]:
        response = await self.__async_execute_with_auth(
            lambda: self.__client.get(
                "/customerapi/api/meteringpoints/meteringpoints",
                headers={
                    "api-version": "1.0",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.__token}",
                },
            )
        )

        if response.is_error:
            logger.error(
                "Failed to get metering points",
                extra={
                    "code": response.status_code,
                    "reason": response.reason_phrase,
                    "response": response.text,
                },
            )

        data = response.json()
        return [MeteringPoint.model_validate(result) for result in data["result"]]

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        if self.__client:
            await self.__client.__aexit__(exc_type, exc_value, traceback)

    async def __ensure_authenticated(self, force=False) -> str | None:
        if self.__token and not force:
            # Reuse token
            logger.debug("Reusing existing token")
            return None
        if not self.__client:
            raise RuntimeError("Session is not open. Use 'async with'")
        response = await self.__client.get(
            "/customerapi/api/token",
            headers={
                "api-version": "1.0",
                "Authorization": f"Bearer {self.__refresh_token}",
            },
        )

        if response.is_error:
            logger.error(
                "Authentication failed",
                extra={
                    "code": response.status_code,
                    "reason": response.reason_phrase,
                    "response": response.text,
                },
            )
            raise RuntimeError(
                f"Authentication Error. Got status code {response.status_code}: {response.reason_phrase}"
            )

        self.__token = response.json()["result"]

    async def __async_execute_with_auth(
        self, cb: Callable[[], Awaitable[httpx.Response]]
    ) -> httpx.Response:
        await self.__ensure_authenticated()
        result = await cb()
        if result.status_code == 401:
            logger.info("Token stale refreshing")
            await self.__ensure_authenticated(force=True)
            result = await cb()
        return result
