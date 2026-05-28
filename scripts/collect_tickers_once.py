"""
Разовый сбор ticker snapshots из Bybit.

Этот скрипт получает текущие рыночные данные по одной или нескольким монетам
и сохраняет их в таблицу tickers.

В tickers сохраняются:
- last_price;
- mark_price;
- index_price;
- high_price_24h;
- low_price_24h;
- price_24h_pcnt;
- volume_24h;
- turnover_24h;
- funding_rate;
- open_interest;
- raw JSON-ответ Bybit.

Скрипт делает один снимок рынка на момент запуска.
Он не работает постоянно.

Запуск для BTCUSDT:

    docker compose run --rm app python scripts/collect_tickers_once.py BTCUSDT

Запуск для нескольких символов:

    docker compose run --rm app python scripts/collect_tickers_once.py BTCUSDT ETHUSDT SOLUSDT

Если symbol не указан, по умолчанию используется BTCUSDT.

Этот скрипт полезен для проверки текущей цены и рыночного состояния.
Позже похожая логика будет запускаться по расписанию через scheduler.
"""

import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from psycopg.types.json import Jsonb

from app.bybit_client import BybitClient
from app.db import get_connection


EXCHANGE = "bybit"
CATEGORY = "linear"


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


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


def insert_ticker(symbol: str, ticker: dict[str, Any], ts: datetime) -> None:
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


def collect_ticker(client: BybitClient, symbol: str, ts: datetime) -> None:
    validate_symbol_exists(symbol)

    result = client.get_tickers(
        category=CATEGORY,
        symbol=symbol,
    )

    rows = result.get("list", [])

    if not rows:
        raise RuntimeError(f"No ticker returned from Bybit for {symbol}")

    ticker = rows[0]

    insert_ticker(
        symbol=symbol,
        ticker=ticker,
        ts=ts,
    )

    print(
        f"{symbol}: "
        f"last={ticker.get('lastPrice')}, "
        f"mark={ticker.get('markPrice')}, "
        f"index={ticker.get('indexPrice')}, "
        f"funding={ticker.get('fundingRate')}, "
        f"oi={ticker.get('openInterest')}"
    )


def main() -> None:
    symbols = [arg.upper() for arg in sys.argv[1:]]

    if not symbols:
        symbols = ["BTCUSDT"]

    client = BybitClient()

    # Один timestamp на весь запуск, чтобы snapshot был логически одной точкой времени.
    ts = datetime.now(timezone.utc).replace(microsecond=0)

    print(f"Collecting tickers at {ts}")
    print(f"Symbols: {', '.join(symbols)}")
    print()

    for symbol in symbols:
        collect_ticker(client, symbol, ts)

    print()
    print(f"Done. Inserted/updated {len(symbols)} ticker snapshots")


if __name__ == "__main__":
    main()