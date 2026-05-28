"""
Историческая загрузка свечей OHLCV из Bybit.

Этот скрипт нужен, чтобы заполнить таблицу candles историческими данными.

Он скачивает свечи частями, потому что Bybit ограничивает количество свечей
за один API-запрос.

Что делает скрипт:
1. Проверяет, что symbol есть в таблице instruments и имеет статус Trading.
2. Рассчитывает период загрузки по количеству дней.
3. Делит период на батчи.
4. Запрашивает свечи у Bybit.
5. Записывает свечи в таблицу candles.
6. При повторном запуске не создает дубли, а обновляет существующие строки.

Запуск:

    docker compose run --rm app python scripts/backfill_candles.py BTCUSDT 60 180

Аргументы:
1. symbol   — торговая пара, например BTCUSDT;
2. interval — интервал свечей:
              1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D;
3. days     — сколько дней истории загрузить.

Примеры:

    docker compose run --rm app python scripts/backfill_candles.py BTCUSDT 60 180
    docker compose run --rm app python scripts/backfill_candles.py ETHUSDT 240 365
    docker compose run --rm app python scripts/backfill_candles.py SOLUSDT D 730

Используется перед аналитикой, чтобы были исторические свечи для расчета EMA, RSI, MACD, ATR и уровней.
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.bybit_client import BybitClient
from app.db import get_connection


EXCHANGE = "bybit"
CATEGORY = "linear"
LIMIT = 1000


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


def datetime_to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def ms_to_datetime_utc(value: str | int) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)


def floor_datetime_to_interval(value: datetime, interval: str) -> datetime:
    """
    Для MVP нормально поддерживаем минутные/часовые интервалы и D.
    Нужно, чтобы не брать текущую незакрытую свечу.
    """
    if interval == "D":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)

    interval_minutes = int(interval)

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


def insert_candles(
    rows: list[list[str]],
    symbol: str,
    interval: str,
) -> int:
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


def backfill_candles(
    symbol: str,
    interval: str,
    days: int,
) -> None:
    if interval not in INTERVAL_TO_MS:
        raise RuntimeError(
            f"Unsupported interval: {interval}. "
            f"Supported intervals: {', '.join(INTERVAL_TO_MS.keys())}"
        )

    validate_symbol_exists(symbol)

    client = BybitClient()

    now_utc = datetime.now(timezone.utc)

    # Не берём текущую незакрытую свечу.
    current_interval_start = floor_datetime_to_interval(now_utc, interval)
    end_ms = datetime_to_ms(current_interval_start) - 1

    start_dt = current_interval_start - timedelta(days=days)
    start_ms = datetime_to_ms(start_dt)

    interval_ms = INTERVAL_TO_MS[interval]
    batch_ms = interval_ms * LIMIT

    print(f"Backfilling candles:")
    print(f"  exchange = {EXCHANGE}")
    print(f"  category = {CATEGORY}")
    print(f"  symbol   = {symbol}")
    print(f"  interval = {interval}")
    print(f"  days     = {days}")
    print(f"  start    = {ms_to_datetime_utc(start_ms)}")
    print(f"  end      = {ms_to_datetime_utc(end_ms)}")
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

        result = client.get_klines(
            category=CATEGORY,
            symbol=symbol,
            interval=interval,
            start=cursor_start_ms,
            end=cursor_end_ms,
            limit=LIMIT,
        )

        rows: list[list[str]] = result.get("list", [])

        if not rows:
            print("  No candles returned")
        else:
            inserted = insert_candles(rows, symbol=symbol, interval=interval)
            total_inserted_or_updated += inserted
            print(f"  Inserted/updated: {inserted}")

        cursor_start_ms = cursor_end_ms + 1
        batch_number += 1

        # Небольшая пауза, чтобы не долбить API.
        time.sleep(0.2)

    print()
    print(f"Done. Total inserted/updated: {total_inserted_or_updated}")


def main() -> None:
    if len(sys.argv) != 4:
        raise RuntimeError(
            "Usage: python scripts/backfill_candles.py SYMBOL INTERVAL DAYS\n"
            "Example: python scripts/backfill_candles.py BTCUSDT 60 180"
        )

    symbol = sys.argv[1].upper()
    interval = sys.argv[2]
    days = int(sys.argv[3])

    if days <= 0:
        raise RuntimeError("DAYS must be greater than 0")

    backfill_candles(
        symbol=symbol,
        interval=interval,
        days=days,
    )


if __name__ == "__main__":
    main()