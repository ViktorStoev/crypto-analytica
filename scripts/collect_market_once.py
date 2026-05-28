"""
Разовый комплексный сбор рыночных данных по symbol.

Этот скрипт объединяет несколько mini-collectors в один запуск.

Он собирает:
- последние закрытые свечи;
- текущий ticker snapshot;
- последние funding rates;
- последние open interest данные, если этот блок включен в текущей версии скрипта.

Это основной ручной скрипт для проверки, что сбор данных по монете работает.

Запуск для BTCUSDT:

    docker compose run --rm app python scripts/collect_market_once.py BTCUSDT

Запуск для нескольких монет:

    docker compose run --rm app python scripts/collect_market_once.py BTCUSDT ETHUSDT SOLUSDT

Если symbol не указан, по умолчанию используется BTCUSDT.

Что важно:
- скрипт делает один проход и завершается;
- он не работает постоянно;
- позже похожая логика будет запускаться автоматически через scheduler.

Используется перед аналитикой, чтобы быстро обновить актуальные данные по монете.
"""

import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from psycopg.types.json import Jsonb

from app.bybit_client import BybitClient
from app.db import get_connection


EXCHANGE = "bybit"
CATEGORY = "linear"

CANDLE_INTERVAL = "60"
OPEN_INTEREST_INTERVAL = "1h"

RECENT_CANDLES_LIMIT = 10
RECENT_FUNDING_LIMIT = 10
RECENT_OPEN_INTEREST_LIMIT = 10


INTERVAL_TO_MS = {
    "1": 60 * 1000,
    "3": 3 * 60 * 1000,
    "5": 5 * 60 * 1000,
    "15": 15 * 60 * 1000,
    "30": 30 * 60 * 1000,
    "60": 60 * 60 * 1000,
    "120": 120 * 60 * 1000,
    "240": 240 * 60 * 1000,
    "360": 360 * 60 * 1000,
    "720": 720 * 60 * 1000,
    "D": 24 * 60 * 60 * 1000,
}


OPEN_INTEREST_INTERVAL_TO_MS = {
    "5min": 5 * 60 * 1000,
    "15min": 15 * 60 * 1000,
    "30min": 30 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def datetime_to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def ms_to_datetime_utc(value: str | int) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)


def floor_datetime_to_candle_interval(value: datetime, interval: str) -> datetime:
    if interval == "D":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)

    interval_minutes = int(interval)

    total_minutes = value.hour * 60 + value.minute
    floored_total_minutes = (total_minutes // interval_minutes) * interval_minutes

    hour = floored_total_minutes // 60
    minute = floored_total_minutes % 60

    return value.replace(hour=hour, minute=minute, second=0, microsecond=0)


def floor_datetime_to_open_interest_interval(value: datetime, interval_time: str) -> datetime:
    if interval_time == "1d":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)

    if interval_time.endswith("min"):
        interval_minutes = int(interval_time.replace("min", ""))
    elif interval_time.endswith("h"):
        interval_minutes = int(interval_time.replace("h", "")) * 60
    else:
        raise RuntimeError(f"Unsupported open interest interval: {interval_time}")

    total_minutes = value.hour * 60 + value.minute
    floored_total_minutes = (total_minutes // interval_minutes) * interval_minutes

    hour = floored_total_minutes // 60
    minute = floored_total_minutes % 60

    return value.replace(hour=hour, minute=minute, second=0, microsecond=0)


def validate_symbol_exists(symbol: str) -> None:
    sql = """
        SELECT 1
        FROM instruments
        WHERE exchange = %s
          AND category = %s
          AND symbol = %s
          AND status = 'Trading'
        LIMIT 1;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (EXCHANGE, CATEGORY, symbol))
            row = cur.fetchone()

    if not row:
        raise RuntimeError(
            f"Symbol {symbol} not found in instruments as Trading. "
            f"Run scripts/sync_instruments.py first or check the symbol name."
        )


def insert_candles(rows: list[list[str]], symbol: str, interval: str) -> int:
    if not rows:
        return 0

    insert_sql = """
        INSERT INTO candles (
            exchange,
            category,
            symbol,
            interval,
            open_time,
            open_price,
            high_price,
            low_price,
            close_price,
            volume,
            turnover
        )
        VALUES (
            %(exchange)s,
            %(category)s,
            %(symbol)s,
            %(interval)s,
            %(open_time)s,
            %(open_price)s,
            %(high_price)s,
            %(low_price)s,
            %(close_price)s,
            %(volume)s,
            %(turnover)s
        )
        ON CONFLICT (exchange, category, symbol, interval, open_time)
        DO UPDATE SET
            open_price = EXCLUDED.open_price,
            high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price,
            close_price = EXCLUDED.close_price,
            volume = EXCLUDED.volume,
            turnover = EXCLUDED.turnover,
            ingested_at = now();
    """

    inserted_or_updated = 0
    rows = sorted(rows, key=lambda row: int(row[0]))

    with get_connection() as conn:
        with conn.cursor() as cur:
            for row in rows:
                params = {
                    "exchange": EXCHANGE,
                    "category": CATEGORY,
                    "symbol": symbol,
                    "interval": interval,
                    "open_time": ms_to_datetime_utc(row[0]),
                    "open_price": Decimal(row[1]),
                    "high_price": Decimal(row[2]),
                    "low_price": Decimal(row[3]),
                    "close_price": Decimal(row[4]),
                    "volume": Decimal(row[5]),
                    "turnover": Decimal(row[6]),
                }

                cur.execute(insert_sql, params)
                inserted_or_updated += 1

        conn.commit()

    return inserted_or_updated


def insert_ticker(symbol: str, ticker: dict[str, Any], ts: datetime) -> int:
    insert_sql = """
        INSERT INTO tickers (
            exchange,
            category,
            symbol,
            ts,
            last_price,
            mark_price,
            index_price,
            high_price_24h,
            low_price_24h,
            prev_price_24h,
            price_24h_pcnt,
            volume_24h,
            turnover_24h,
            funding_rate,
            open_interest,
            raw
        )
        VALUES (
            %(exchange)s,
            %(category)s,
            %(symbol)s,
            %(ts)s,
            %(last_price)s,
            %(mark_price)s,
            %(index_price)s,
            %(high_price_24h)s,
            %(low_price_24h)s,
            %(prev_price_24h)s,
            %(price_24h_pcnt)s,
            %(volume_24h)s,
            %(turnover_24h)s,
            %(funding_rate)s,
            %(open_interest)s,
            %(raw)s
        )
        ON CONFLICT (exchange, category, symbol, ts)
        DO UPDATE SET
            last_price = EXCLUDED.last_price,
            mark_price = EXCLUDED.mark_price,
            index_price = EXCLUDED.index_price,
            high_price_24h = EXCLUDED.high_price_24h,
            low_price_24h = EXCLUDED.low_price_24h,
            prev_price_24h = EXCLUDED.prev_price_24h,
            price_24h_pcnt = EXCLUDED.price_24h_pcnt,
            volume_24h = EXCLUDED.volume_24h,
            turnover_24h = EXCLUDED.turnover_24h,
            funding_rate = EXCLUDED.funding_rate,
            open_interest = EXCLUDED.open_interest,
            raw = EXCLUDED.raw,
            ingested_at = now();
    """

    params = {
        "exchange": EXCHANGE,
        "category": CATEGORY,
        "symbol": symbol,
        "ts": ts,
        "last_price": to_decimal(ticker.get("lastPrice")),
        "mark_price": to_decimal(ticker.get("markPrice")),
        "index_price": to_decimal(ticker.get("indexPrice")),
        "high_price_24h": to_decimal(ticker.get("highPrice24h")),
        "low_price_24h": to_decimal(ticker.get("lowPrice24h")),
        "prev_price_24h": to_decimal(ticker.get("prevPrice24h")),
        "price_24h_pcnt": to_decimal(ticker.get("price24hPcnt")),
        "volume_24h": to_decimal(ticker.get("volume24h")),
        "turnover_24h": to_decimal(ticker.get("turnover24h")),
        "funding_rate": to_decimal(ticker.get("fundingRate")),
        "open_interest": to_decimal(ticker.get("openInterest")),
        "raw": Jsonb(ticker),
    }

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(insert_sql, params)

        conn.commit()

    return 1


def insert_funding_rows(rows: list[dict[str, Any]], symbol: str) -> int:
    if not rows:
        return 0

    insert_sql = """
        INSERT INTO funding_rates (
            exchange,
            category,
            symbol,
            funding_time,
            funding_rate,
            raw
        )
        VALUES (
            %(exchange)s,
            %(category)s,
            %(symbol)s,
            %(funding_time)s,
            %(funding_rate)s,
            %(raw)s
        )
        ON CONFLICT (exchange, category, symbol, funding_time)
        DO UPDATE SET
            funding_rate = EXCLUDED.funding_rate,
            raw = EXCLUDED.raw,
            ingested_at = now();
    """

    inserted_or_updated = 0
    rows = sorted(rows, key=lambda row: int(row["fundingRateTimestamp"]))

    with get_connection() as conn:
        with conn.cursor() as cur:
            for row in rows:
                params = {
                    "exchange": EXCHANGE,
                    "category": CATEGORY,
                    "symbol": symbol,
                    "funding_time": ms_to_datetime_utc(row["fundingRateTimestamp"]),
                    "funding_rate": Decimal(row["fundingRate"]),
                    "raw": Jsonb(row),
                }

                cur.execute(insert_sql, params)
                inserted_or_updated += 1

        conn.commit()

    return inserted_or_updated


def insert_open_interest_rows(
    rows: list[dict[str, Any]],
    symbol: str,
    interval_time: str,
) -> int:
    if not rows:
        return 0

    insert_sql = """
        INSERT INTO open_interest (
            exchange,
            category,
            symbol,
            interval,
            ts,
            open_interest,
            raw
        )
        VALUES (
            %(exchange)s,
            %(category)s,
            %(symbol)s,
            %(interval)s,
            %(ts)s,
            %(open_interest)s,
            %(raw)s
        )
        ON CONFLICT (exchange, category, symbol, interval, ts)
        DO UPDATE SET
            open_interest = EXCLUDED.open_interest,
            raw = EXCLUDED.raw,
            ingested_at = now();
    """

    inserted_or_updated = 0
    rows = sorted(rows, key=lambda row: int(row["timestamp"]))

    with get_connection() as conn:
        with conn.cursor() as cur:
            for row in rows:
                params = {
                    "exchange": EXCHANGE,
                    "category": CATEGORY,
                    "symbol": symbol,
                    "interval": interval_time,
                    "ts": ms_to_datetime_utc(row["timestamp"]),
                    "open_interest": Decimal(row["openInterest"]),
                    "raw": Jsonb(row),
                }

                cur.execute(insert_sql, params)
                inserted_or_updated += 1

        conn.commit()

    return inserted_or_updated


def collect_recent_candles(client: BybitClient, symbol: str) -> int:
    now_utc = datetime.now(timezone.utc)
    current_interval_start = floor_datetime_to_candle_interval(now_utc, CANDLE_INTERVAL)

    result = client.get_klines(
        category=CATEGORY,
        symbol=symbol,
        interval=CANDLE_INTERVAL,
        limit=RECENT_CANDLES_LIMIT,
    )

    rows = result.get("list", [])

    closed_rows = [
        row for row in rows
        if ms_to_datetime_utc(row[0]) < current_interval_start
    ]

    return insert_candles(
        rows=closed_rows,
        symbol=symbol,
        interval=CANDLE_INTERVAL,
    )


def collect_ticker(client: BybitClient, symbol: str, ts: datetime) -> int:
    result = client.get_tickers(
        category=CATEGORY,
        symbol=symbol,
    )

    rows = result.get("list", [])

    if not rows:
        raise RuntimeError(f"No ticker returned from Bybit for {symbol}")

    return insert_ticker(
        symbol=symbol,
        ticker=rows[0],
        ts=ts,
    )


def collect_recent_funding_rates(client: BybitClient, symbol: str) -> int:
    now_utc = datetime.now(timezone.utc)
    end_ms = datetime_to_ms(now_utc)

    result = client.get_funding_history(
        category=CATEGORY,
        symbol=symbol,
        end_time=end_ms,
        limit=RECENT_FUNDING_LIMIT,
    )

    rows = result.get("list", [])

    return insert_funding_rows(
        rows=rows,
        symbol=symbol,
    )


def collect_recent_open_interest(client: BybitClient, symbol: str) -> int:
    now_utc = datetime.now(timezone.utc)
    current_interval_start = floor_datetime_to_open_interest_interval(
        now_utc,
        OPEN_INTEREST_INTERVAL,
    )

    interval_ms = OPEN_INTEREST_INTERVAL_TO_MS[OPEN_INTEREST_INTERVAL]

    end_ms = datetime_to_ms(current_interval_start) - 1
    start_ms = end_ms - (interval_ms * RECENT_OPEN_INTEREST_LIMIT) + 1

    result = client.get_open_interest(
        category=CATEGORY,
        symbol=symbol,
        interval_time=OPEN_INTEREST_INTERVAL,
        start_time=start_ms,
        end_time=end_ms,
        limit=RECENT_OPEN_INTEREST_LIMIT,
    )

    rows = result.get("list", [])

    return insert_open_interest_rows(
        rows=rows,
        symbol=symbol,
        interval_time=OPEN_INTEREST_INTERVAL,
    )


def collect_market_for_symbol(client: BybitClient, symbol: str, ticker_ts: datetime) -> None:
    validate_symbol_exists(symbol)

    print(f"Collecting market data for {symbol}...")

    candles_count = collect_recent_candles(client, symbol)
    print(f"  candles inserted/updated       = {candles_count}")

    ticker_count = collect_ticker(client, symbol, ticker_ts)
    print(f"  ticker snapshots inserted      = {ticker_count}")

    funding_count = collect_recent_funding_rates(client, symbol)
    print(f"  funding rates inserted/updated = {funding_count}")

    open_interest_count = collect_recent_open_interest(client, symbol)
    print(f"  open interest inserted/updated = {open_interest_count}")

    print()


def main() -> None:
    symbols = [arg.upper() for arg in sys.argv[1:]]

    if not symbols:
        symbols = ["BTCUSDT"]

    client = BybitClient()

    ticker_ts = datetime.now(timezone.utc).replace(microsecond=0)

    print("Collecting market data once")
    print(f"Ticker snapshot timestamp: {ticker_ts}")
    print(f"Symbols: {', '.join(symbols)}")
    print()

    for symbol in symbols:
        collect_market_for_symbol(
            client=client,
            symbol=symbol,
            ticker_ts=ticker_ts,
        )

        time.sleep(0.2)

    print("Done.")


if __name__ == "__main__":
    main()