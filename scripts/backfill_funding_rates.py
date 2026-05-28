"""
Историческая загрузка funding rate из Bybit.

Funding rate показывает, кто платит комиссию на perpetual-фьючерсах:
лонги или шорты.

Этот скрипт заполняет таблицу funding_rates историческими значениями funding.

Что делает скрипт:
1. Проверяет, что symbol есть в таблице instruments.
2. Берет fundingInterval из instruments.raw.
3. Рассчитывает период загрузки по количеству дней.
4. Делит период на батчи.
5. Запрашивает funding history у Bybit.
6. Записывает данные в таблицу funding_rates.
7. При повторном запуске обновляет существующие строки без дублей.

Запуск:

    docker compose run --rm app python scripts/backfill_funding_rates.py BTCUSDT 180

Аргументы:
1. symbol — торговая пара, например BTCUSDT;
2. days   — сколько дней истории загрузить.

Пример:

    docker compose run --rm app python scripts/backfill_funding_rates.py ETHUSDT 90

Используется для аналитики перегрева рынка:
- сильно положительный funding может говорить о перегреве лонгов;
- сильно отрицательный funding может говорить о перегреве шортов.
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.bybit_client import BybitClient
from app.db import get_connection


EXCHANGE = "bybit"
CATEGORY = "linear"
LIMIT = 200


def datetime_to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def ms_to_datetime_utc(value: str | int) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)


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


def get_funding_interval_minutes(symbol: str) -> int:
    """
    Bybit хранит fundingInterval в instruments-info.
    Обычно для perpetual это 480 минут, то есть 8 часов.
    Но лучше читать из instruments.raw, а не хардкодить.
    """
    sql = """
        SELECT raw->>'fundingInterval' AS funding_interval
        FROM instruments
        WHERE exchange = %s
          AND category = %s
          AND symbol = %s
        LIMIT 1;
    """

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (EXCHANGE, CATEGORY, symbol))
            row = cur.fetchone()

    if not row or not row["funding_interval"]:
        return 480

    return int(row["funding_interval"])


def insert_funding_rows(
    rows: list[dict[str, Any]],
    symbol: str,
) -> int:
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


def backfill_funding_rates(symbol: str, days: int) -> None:
    validate_symbol_exists(symbol)

    client = BybitClient()

    now_utc = datetime.now(timezone.utc)
    end_ms = datetime_to_ms(now_utc)
    start_ms = datetime_to_ms(now_utc - timedelta(days=days))

    funding_interval_minutes = get_funding_interval_minutes(symbol)
    funding_interval_ms = funding_interval_minutes * 60 * 1000

    # Берём окно чуть меньше или равно 200 funding-событий.
    batch_ms = funding_interval_ms * LIMIT

    print("Backfilling funding rates:")
    print(f"  exchange          = {EXCHANGE}")
    print(f"  category          = {CATEGORY}")
    print(f"  symbol            = {symbol}")
    print(f"  days              = {days}")
    print(f"  funding_interval  = {funding_interval_minutes} minutes")
    print(f"  start             = {ms_to_datetime_utc(start_ms)}")
    print(f"  end               = {ms_to_datetime_utc(end_ms)}")
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

        result = client.get_funding_history(
            category=CATEGORY,
            symbol=symbol,
            start_time=cursor_start_ms,
            end_time=cursor_end_ms,
            limit=LIMIT,
        )

        rows = result.get("list", [])

        if not rows:
            print("  No funding rates returned")
        else:
            inserted = insert_funding_rows(rows, symbol=symbol)
            total_inserted_or_updated += inserted
            print(f"  Inserted/updated: {inserted}")

        cursor_start_ms = cursor_end_ms + 1
        batch_number += 1

        time.sleep(0.2)

    print()
    print(f"Done. Total inserted/updated: {total_inserted_or_updated}")


def main() -> None:
    if len(sys.argv) != 3:
        raise RuntimeError(
            "Usage: python scripts/backfill_funding_rates.py SYMBOL DAYS\n"
            "Example: python scripts/backfill_funding_rates.py BTCUSDT 180"
        )

    symbol = sys.argv[1].upper()
    days = int(sys.argv[2])

    if days <= 0:
        raise RuntimeError("DAYS must be greater than 0")

    backfill_funding_rates(
        symbol=symbol,
        days=days,
    )


if __name__ == "__main__":
    main()