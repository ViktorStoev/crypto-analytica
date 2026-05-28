"""
Историческая загрузка Open Interest из Bybit.

Open Interest показывает общий объем открытых фьючерсных позиций.

Этот скрипт заполняет таблицу open_interest историческими значениями OI.

Что делает скрипт:
1. Проверяет, что symbol есть в таблице instruments.
2. Рассчитывает период загрузки по количеству дней.
3. Делит период на батчи.
4. Запрашивает open interest у Bybit.
5. Записывает данные в таблицу open_interest.
6. При повторном запуске обновляет существующие строки без дублей.

Запуск:

    docker compose run --rm app python scripts/backfill_open_interest.py BTCUSDT 1h 180

Аргументы:
1. symbol        — торговая пара, например BTCUSDT;
2. interval_time — интервал open interest:
                   5min, 15min, 30min, 1h, 4h, 1d;
3. days          — сколько дней истории загрузить.

Примеры:

    docker compose run --rm app python scripts/backfill_open_interest.py BTCUSDT 1h 180
    docker compose run --rm app python scripts/backfill_open_interest.py ETHUSDT 4h 365

Используется для анализа деривативов:
- цена растет и OI растет — в движение входят новые позиции;
- цена растет и OI падает — возможно закрытие шортов;
- цена падает и OI растет — возможно открываются новые шорты;
- цена падает и OI падает — позиции закрываются.
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from app.bybit_client import BybitClient
from app.db import get_connection


EXCHANGE = "bybit"
CATEGORY = "linear"
LIMIT = 200


INTERVAL_TIME_TO_MS = {
    "5min": 5 * 60 * 1000,
    "15min": 15 * 60 * 1000,
    "30min": 30 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


def datetime_to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def ms_to_datetime_utc(value: str | int) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)


def floor_datetime_to_interval_time(value: datetime, interval_time: str) -> datetime:
    if interval_time == "1d":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)

    if interval_time.endswith("min"):
        interval_minutes = int(interval_time.replace("min", ""))
    elif interval_time.endswith("h"):
        interval_minutes = int(interval_time.replace("h", "")) * 60
    else:
        raise RuntimeError(f"Unsupported interval_time: {interval_time}")

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


def backfill_open_interest(
    symbol: str,
    interval_time: str,
    days: int,
) -> None:
    if interval_time not in INTERVAL_TIME_TO_MS:
        raise RuntimeError(
            f"Unsupported interval_time: {interval_time}. "
            f"Supported values: {', '.join(INTERVAL_TIME_TO_MS.keys())}"
        )

    validate_symbol_exists(symbol)

    client = BybitClient()

    now_utc = datetime.now(timezone.utc)

    # Не берём текущий незакрытый интервал.
    current_interval_start = floor_datetime_to_interval_time(now_utc, interval_time)
    end_ms = datetime_to_ms(current_interval_start) - 1

    start_dt = current_interval_start - timedelta(days=days)
    start_ms = datetime_to_ms(start_dt)

    interval_ms = INTERVAL_TIME_TO_MS[interval_time]
    batch_ms = interval_ms * LIMIT

    print("Backfilling open interest:")
    print(f"  exchange      = {EXCHANGE}")
    print(f"  category      = {CATEGORY}")
    print(f"  symbol        = {symbol}")
    print(f"  interval_time = {interval_time}")
    print(f"  days          = {days}")
    print(f"  start         = {ms_to_datetime_utc(start_ms)}")
    print(f"  end           = {ms_to_datetime_utc(end_ms)}")
    print()

    total_inserted_or_updated = 0
    batch_number = 1
    cursor_start_ms = start_ms

    while cursor_start_ms <= end_ms:
        cursor_end_ms = min(cursor_start_ms + batch_ms - 1, end_ms)

        print(
            f"Batch {batch_number}: "
            f"{ms_to_datetime_utc(cursor_start_ms)} -> {ms_to_datetime_utc(cursor_end_ms)}"
        )

        result = client.get_open_interest(
            category=CATEGORY,
            symbol=symbol,
            interval_time=interval_time,
            start_time=cursor_start_ms,
            end_time=cursor_end_ms,
            limit=LIMIT,
        )

        rows = result.get("list", [])

        if not rows:
            print("  No open interest returned")
        else:
            inserted = insert_open_interest_rows(
                rows,
                symbol=symbol,
                interval_time=interval_time,
            )
            total_inserted_or_updated += inserted
            print(f"  Inserted/updated: {inserted}")

        cursor_start_ms = cursor_end_ms + 1
        batch_number += 1

        time.sleep(0.2)

    print()
    print(f"Done. Total inserted/updated: {total_inserted_or_updated}")


def main() -> None:
    if len(sys.argv) != 4:
        raise RuntimeError(
            "Usage: python scripts/backfill_open_interest.py SYMBOL INTERVAL_TIME DAYS\n"
            "Example: python scripts/backfill_open_interest.py BTCUSDT 1h 180"
        )

    symbol = sys.argv[1].upper()
    interval_time = sys.argv[2]
    days = int(sys.argv[3])

    if days <= 0:
        raise RuntimeError("DAYS must be greater than 0")

    backfill_open_interest(
        symbol=symbol,
        interval_time=interval_time,
        days=days,
    )


if __name__ == "__main__":
    main()