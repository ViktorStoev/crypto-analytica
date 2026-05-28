"""
Синхронизация списка торговых инструментов Bybit.

Этот скрипт запрашивает у Bybit список доступных linear-инструментов
и сохраняет их в таблицу instruments.

Таблица instruments нужна, чтобы проект знал:
- какие символы реально существуют;
- какие из них находятся в статусе Trading;
- какой у инструмента base_coin, quote_coin, settle_coin;
- какой tick_size и qty_step;
- какой fundingInterval хранится в raw.

Этот скрипт желательно запускать перед backfill-скриптами,
потому что другие скрипты проверяют, что symbol существует в instruments.

Запуск:

    docker compose run --rm app python scripts/sync_instruments.py

Ожидаемый результат:

    Inserted/updated N bybit linear instruments

Когда запускать:
- первый раз после создания базы;
- периодически, если нужно обновить список инструментов;
- перед добавлением новых монет в сбор.
"""

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


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fetch_all_instruments(client: BybitClient, category: str) -> list[dict[str, Any]]:
    instruments: list[dict[str, Any]] = []
    cursor: str | None = None
    page = 1

    while True:
        print(f"Downloading instruments page {page}...")

        result = client.get_instruments_info(
            category=category,
            status="Trading",
            limit=1000,
            cursor=cursor,
        )

        rows = result.get("list", [])
        instruments.extend(rows)

        cursor = result.get("nextPageCursor")

        if not cursor:
            break

        page += 1

    return instruments


def main() -> None:
    client = BybitClient()

    instruments = fetch_all_instruments(client, CATEGORY)

    if not instruments:
        raise RuntimeError("No instruments returned from Bybit")

    insert_sql = """
        INSERT INTO instruments (
            exchange,
            category,
            symbol,
            base_coin,
            quote_coin,
            settle_coin,
            contract_type,
            status,
            price_scale,
            tick_size,
            qty_step,
            min_order_qty,
            max_order_qty,
            launch_time_ms,
            delivery_time_ms,
            raw,
            updated_at
        )
        VALUES (
            %(exchange)s,
            %(category)s,
            %(symbol)s,
            %(base_coin)s,
            %(quote_coin)s,
            %(settle_coin)s,
            %(contract_type)s,
            %(status)s,
            %(price_scale)s,
            %(tick_size)s,
            %(qty_step)s,
            %(min_order_qty)s,
            %(max_order_qty)s,
            %(launch_time_ms)s,
            %(delivery_time_ms)s,
            %(raw)s,
            now()
        )
        ON CONFLICT (exchange, category, symbol)
        DO UPDATE SET
            base_coin = EXCLUDED.base_coin,
            quote_coin = EXCLUDED.quote_coin,
            settle_coin = EXCLUDED.settle_coin,
            contract_type = EXCLUDED.contract_type,
            status = EXCLUDED.status,
            price_scale = EXCLUDED.price_scale,
            tick_size = EXCLUDED.tick_size,
            qty_step = EXCLUDED.qty_step,
            min_order_qty = EXCLUDED.min_order_qty,
            max_order_qty = EXCLUDED.max_order_qty,
            launch_time_ms = EXCLUDED.launch_time_ms,
            delivery_time_ms = EXCLUDED.delivery_time_ms,
            raw = EXCLUDED.raw,
            updated_at = now();
    """

    inserted_or_updated = 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            for item in instruments:
                price_filter = item.get("priceFilter") or {}
                lot_size_filter = item.get("lotSizeFilter") or {}

                params = {
                    "exchange": EXCHANGE,
                    "category": CATEGORY,
                    "symbol": item.get("symbol"),
                    "base_coin": item.get("baseCoin"),
                    "quote_coin": item.get("quoteCoin"),
                    "settle_coin": item.get("settleCoin"),
                    "contract_type": item.get("contractType"),
                    "status": item.get("status"),
                    "price_scale": to_int(item.get("priceScale")),
                    "tick_size": to_decimal(price_filter.get("tickSize")),
                    "qty_step": to_decimal(lot_size_filter.get("qtyStep")),
                    "min_order_qty": to_decimal(lot_size_filter.get("minOrderQty")),
                    "max_order_qty": to_decimal(lot_size_filter.get("maxOrderQty")),
                    "launch_time_ms": to_int(item.get("launchTime")),
                    "delivery_time_ms": to_int(item.get("deliveryTime")),
                    "raw": Jsonb(item),
                }

                if not params["symbol"]:
                    continue

                cur.execute(insert_sql, params)
                inserted_or_updated += 1

        conn.commit()

    print(f"Inserted/updated {inserted_or_updated} {EXCHANGE} {CATEGORY} instruments")


if __name__ == "__main__":
    main()