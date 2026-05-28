"""
Проверка публичного Bybit API.

Этот скрипт нужен для быстрой проверки, что:
- app-контейнер запускается;
- Python видит модуль app;
- Bybit API доступен;
- Bybit возвращает ticker по BTCUSDT;
- Bybit возвращает последние свечи BTCUSDT.

Скрипт ничего не записывает в базу данных.
Он только печатает результат в консоль.

Запуск:

    docker compose run --rm app python scripts/check_bybit_public.py

Ожидаемый результат:
- выводится текущая цена BTCUSDT;
- выводится funding rate;
- выводится open interest;
- выводятся последние 5 часовых свечей BTCUSDT.

Использовать этот скрипт удобно после изменений в Docker, BybitClient или окружении.
"""

from app.bybit_client import BybitClient


def main() -> None:
    client = BybitClient()

    category = "linear"
    symbol = "BTCUSDT"
    interval = "60"

    print("Checking Bybit public API...")
    print(f"Symbol: {symbol}")
    print(f"Category: {category}")
    print()

    ticker_result = client.get_tickers(category=category, symbol=symbol)
    ticker_list = ticker_result.get("list", [])

    if not ticker_list:
        raise RuntimeError("Ticker list is empty")

    ticker = ticker_list[0]

    print("Ticker:")
    print(f"  lastPrice      = {ticker.get('lastPrice')}")
    print(f"  markPrice      = {ticker.get('markPrice')}")
    print(f"  indexPrice     = {ticker.get('indexPrice')}")
    print(f"  price24hPcnt   = {ticker.get('price24hPcnt')}")
    print(f"  volume24h      = {ticker.get('volume24h')}")
    print(f"  turnover24h    = {ticker.get('turnover24h')}")
    print(f"  fundingRate    = {ticker.get('fundingRate')}")
    print(f"  openInterest   = {ticker.get('openInterest')}")
    print()

    kline_result = client.get_klines(
        category=category,
        symbol=symbol,
        interval=interval,
        limit=5,
    )

    candles = kline_result.get("list", [])

    if not candles:
        raise RuntimeError("Kline list is empty")

    candles = sorted(candles, key=lambda row: int(row[0]))

    print("Last 5 BTCUSDT 1h candles from Bybit:")
    for row in candles:
        start_time_ms = row[0]
        open_price = row[1]
        high_price = row[2]
        low_price = row[3]
        close_price = row[4]
        volume = row[5]
        turnover = row[6]

        print(
            f"  startTimeMs={start_time_ms}, "
            f"open={open_price}, high={high_price}, low={low_price}, "
            f"close={close_price}, volume={volume}, turnover={turnover}"
        )


if __name__ == "__main__":
    main()