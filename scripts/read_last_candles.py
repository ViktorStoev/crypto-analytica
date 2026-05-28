"""
Чтение последних свечей из базы данных.

Этот скрипт проверяет, что данные действительно лежат в PostgreSQL/TimescaleDB,
а не просто были получены с Bybit.

По умолчанию читает последние 10 свечей BTCUSDT с интервалом 60 минут.

Запуск по умолчанию:

    docker compose run --rm app python scripts/read_last_candles.py

Запуск с параметрами:

    docker compose run --rm app python scripts/read_last_candles.py BTCUSDT 60 10
    docker compose run --rm app python scripts/read_last_candles.py ETHUSDT 60 20

Аргументы:
1. symbol   — торговая пара, например BTCUSDT;
2. interval — интервал свечей, например 60;
3. limit    — сколько последних свечей вывести.

Скрипт ничего не скачивает с Bybit.
Он только читает таблицу candles.
"""

import sys

from psycopg.rows import dict_row

from app.db import get_connection


EXCHANGE = "bybit"
CATEGORY = "linear"


def main() -> None:
    symbol = sys.argv[1].upper() if len(sys.argv) >= 2 else "BTCUSDT"
    interval = sys.argv[2] if len(sys.argv) >= 3 else "60"
    limit = int(sys.argv[3]) if len(sys.argv) >= 4 else 10

    sql = """
        SELECT
            open_time,
            open_price,
            high_price,
            low_price,
            close_price,
            volume
        FROM candles
        WHERE exchange = %s
          AND category = %s
          AND symbol = %s
          AND interval = %s
        ORDER BY open_time DESC
        LIMIT %s;
    """

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (EXCHANGE, CATEGORY, symbol, interval, limit))
            rows = cur.fetchall()

    if not rows:
        print(f"No candles found in DB for {symbol} interval={interval}")
        return

    print(f"Last {limit} {symbol} {interval} candles from PostgreSQL:")

    for row in rows:
        print(
            f"{row['open_time']} | "
            f"O={row['open_price']} "
            f"H={row['high_price']} "
            f"L={row['low_price']} "
            f"C={row['close_price']} "
            f"V={row['volume']}"
        )


if __name__ == "__main__":
    main()