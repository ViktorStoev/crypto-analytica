"""
Минимальный Bybit REST API client.

Этот файл отвечает за обращение к публичному Bybit API.

Через этот клиент проект получает рыночные данные:
- список торговых инструментов;
- свечи OHLCV;
- tickers;
- funding rate;
- open interest.

Этот файл НЕ записывает данные в БД.
Он только делает HTTP-запросы к Bybit и возвращает результат в Python-формате.

Дальше эти данные используют скрипты из папки scripts/.

Основные методы:
- get_instruments_info() — получить список торговых инструментов;
- get_klines() — получить свечи;
- get_tickers() — получить текущие рыночные данные;
- get_funding_history() — получить историю funding rate;
- get_open_interest() — получить историю open interest.

Запускать этот файл отдельно не нужно.

Проверка клиента выполняется через:

    docker compose run --rm app python scripts/check_bybit_public.py
"""

from typing import Any
import time

import requests

from app.config import BYBIT_BASE_URL


class BybitApiError(RuntimeError):
    pass


class BybitRateLimitError(BybitApiError):
    pass


class BybitClient:
    def __init__(
        self,
        base_url: str = BYBIT_BASE_URL,
        timeout: int = 10,
        max_retries: int = 3,
        retry_sleep_seconds: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_sleep_seconds = retry_sleep_seconds
        self.session = requests.Session()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        url = f"{self.base_url}{path}"

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                )

                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = BybitApiError(
                        f"Temporary HTTP error: status={response.status_code}, "
                        f"path={path}, params={params}"
                    )
                    time.sleep(self.retry_sleep_seconds * attempt)
                    continue

                response.raise_for_status()

                data = response.json()

                ret_code = data.get("retCode")
                ret_msg = data.get("retMsg")

                if ret_code == 10006:
                    reset_ts = response.headers.get("X-Bapi-Limit-Reset-Timestamp")
                    raise BybitRateLimitError(
                        f"Bybit rate limit: retCode={ret_code}, retMsg={ret_msg}, "
                        f"reset={reset_ts}, path={path}, params={params}"
                    )

                if ret_code != 0:
                    raise BybitApiError(
                        f"Bybit API error: retCode={ret_code}, retMsg={ret_msg}, "
                        f"path={path}, params={params}"
                    )

                return data.get("result", {})

            except BybitRateLimitError:
                # Для MVP просто ждём чуть дольше.
                # Позже можно читать X-Bapi-Limit-Reset-Timestamp и спать точнее.
                if attempt == self.max_retries:
                    raise
                time.sleep(3 * attempt)

            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                time.sleep(self.retry_sleep_seconds * attempt)

        raise BybitApiError(
            f"Bybit request failed after {self.max_retries} attempts: "
            f"path={path}, params={params}, last_error={last_error}"
        )

    def get_instruments_info(
        self,
        category: str,
        symbol: str | None = None,
        status: str | None = "Trading",
        limit: int = 1000,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "category": category,
            "limit": limit,
        }

        if symbol:
            params["symbol"] = symbol

        if status:
            params["status"] = status

        if cursor:
            params["cursor"] = cursor

        return self._get("/v5/market/instruments-info", params)

    def get_tickers(
        self,
        category: str,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "category": category,
        }

        if symbol:
            params["symbol"] = symbol

        return self._get("/v5/market/tickers", params)

    def get_klines(
        self,
        category: str,
        symbol: str,
        interval: str,
        start: int | None = None,
        end: int | None = None,
        limit: int = 1000,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }

        if start is not None:
            params["start"] = start

        if end is not None:
            params["end"] = end

        return self._get("/v5/market/kline", params)

    def get_funding_history(
        self,
        category: str,
        symbol: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "limit": limit,
        }

        if start_time is not None:
            params["startTime"] = start_time

        if end_time is not None:
            params["endTime"] = end_time

        return self._get("/v5/market/funding/history", params)

    def get_open_interest(
        self,
        category: str,
        symbol: str,
        interval_time: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 200,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "intervalTime": interval_time,
            "limit": limit,
        }

        if start_time is not None:
            params["startTime"] = start_time

        if end_time is not None:
            params["endTime"] = end_time

        if cursor:
            params["cursor"] = cursor

        return self._get("/v5/market/open-interest", params)