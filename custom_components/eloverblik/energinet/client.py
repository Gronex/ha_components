import logging
from collections.abc import Awaitable, Callable
from datetime import date
from types import TracebackType
from typing import Literal

import httpx

from .models import EnergyDataResponse, MeteringPoint, ResponseItem

logger = logging.getLogger(__name__)

Aggregation = Literal["Actual", "Quarter", "Hour", "Day", "Month", "Year"]


class EnerginetClient:
    """Client for the Eloverblik / Energinet customer API.

    Supports use as an async context manager (``async with``) for short-lived
    sessions, as well as explicit :meth:`open` / :meth:`close` for long-lived
    hosts such as a Home Assistant DataUpdateCoordinator.
    """

    _token: str | None
    _client: httpx.AsyncClient | None
    _refresh_token: str

    def __init__(self, refresh_token: str) -> None:
        self._token = None
        self._refresh_token = refresh_token
        self._client = None

    async def open(self) -> None:
        """Open the underlying HTTP session.

        Safe to call when already open (idempotent).
        """
        if self._client is not None:
            return
        client = httpx.AsyncClient(base_url="https://api.eloverblik.dk", timeout=60)
        # AsyncClient.__aenter__ returns the client itself; assign to satisfy
        # call-result checks and keep the reference we just entered.
        self._client = await client.__aenter__()

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def __aenter__(self) -> "EnerginetClient":
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self.close()

    async def async_get_timeseries(
        self,
        from_date: date,
        to_date: date,
        aggregation: Aggregation,
        metering_points: list[str],
    ) -> list[ResponseItem]:
        client = self._require_session()
        response = await self._execute_with_auth(
            lambda: client.post(
                f"/customerapi/api/meterdata/gettimeseries/{from_date}/{to_date}/{aggregation}",
                headers=self._auth_headers(),
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
        client = self._require_session()
        response = await self._execute_with_auth(
            lambda: client.get(
                "/customerapi/api/meteringpoints/meteringpoints",
                headers=self._auth_headers(),
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
            return []

        data = response.json()
        return [MeteringPoint.model_validate(result) for result in data["result"]]

    def _require_session(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "Client is not open. Call 'await open()' or use 'async with'."
            )
        return self._client

    def _auth_headers(self) -> dict[str, str]:
        return {
            "api-version": "1.0",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }

    async def _ensure_authenticated(self, force: bool = False) -> None:
        if self._token and not force:
            logger.debug("Reusing existing token")
            return
        client = self._require_session()
        response = await client.get(
            "/customerapi/api/token",
            headers={
                "api-version": "1.0",
                "Authorization": f"Bearer {self._refresh_token}",
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

        self._token = response.json()["result"]

    async def _execute_with_auth(
        self, cb: Callable[[], Awaitable[httpx.Response]]
    ) -> httpx.Response:
        await self._ensure_authenticated()
        result = await cb()
        if result.status_code == 401:
            logger.info("Token stale, refreshing")
            await self._ensure_authenticated(force=True)
            result = await cb()
        return result
