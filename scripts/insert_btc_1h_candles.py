from datetime import datetime, timezone
from decimal import Decimal

from app.bybit_client import BybitClient
from app.db import get_connection


EXCHANGE = "bybit"
CATEGORY = "linear"
SYMBOL = "BTCUSDT"
INTERVAL = "60"
LIMIT = 200


def ms_to_datetime_utc(value: str) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)


def main() -> None:
    client = BybitClient()

    print(f"Downloading {SYMBOL} {INTERVAL} candles from Bybit...")

    result = client.get_klines(
        category=CATEGORY,
        symbol=SYMBOL,
        interval=INTERVAL,
        limit=LIMIT,
    )

    rows = result.get("list", [])

    if not rows:
        raise RuntimeError("No candles returned from Bybit")

    rows = sorted(rows, key=lambda row: int(row[0]))

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

    with get_connection() as conn:
        with conn.cursor() as cur:
            for row in rows:
                params = {
                    "exchange": EXCHANGE,
                    "category": CATEGORY,
                    "symbol": SYMBOL,
                    "interval": INTERVAL,
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

    print(f"Inserted/updated {inserted_or_updated} {SYMBOL} {INTERVAL} candles")


if __name__ == "__main__":
    main()