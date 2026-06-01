"""
Слой загрузки данных для analytics.

Этот модуль НЕ анализирует рынок.
Его задача — только достать данные из PostgreSQL/TimescaleDB
и вернуть их в удобном виде для аналитических модулей.
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd
from sqlalchemy import text

from app.analytics.utils import safe_float


def get_database_url() -> str:
    """
    Возвращает строку подключения к PostgreSQL.

    Важно:
    у нас установлен psycopg v3, поэтому для SQLAlchemy используем:
    postgresql+psycopg://...
    """

    database_url = os.getenv("DATABASE_URL")

    if database_url:
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace(
                "postgresql://",
                "postgresql+psycopg://",
                1,
            )

        if database_url.startswith("postgres://"):
            database_url = database_url.replace(
                "postgres://",
                "postgresql+psycopg://",
                1,
            )

        return database_url

    db_user = os.getenv("POSTGRES_USER", "crypto_app")
    db_password = os.getenv("POSTGRES_PASSWORD", "crypto_app")
    db_host = os.getenv("POSTGRES_HOST", "timescaledb")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "crypto_market")

    return f"postgresql+psycopg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


def normalize_open_interest_interval(candle_interval: str) -> str:
    """
    В candles Bybit interval хранится как '60'.
    В open_interest Bybit interval хранится как '1h'.

    Поэтому для анализа BTCUSDT 60 нужно читать open_interest BTCUSDT 1h.
    """

    mapping = {
        "1": "5min",
        "5": "5min",
        "15": "15min",
        "30": "30min",
        "60": "1h",
        "120": "2h",
        "240": "4h",
        "360": "6h",
        "720": "12h",
        "D": "1d",
        "1D": "1d",
    }

    return mapping.get(candle_interval, candle_interval)


def get_latest_market_row(engine, symbol: str, interval: str) -> Optional[dict]:
    """
    Берём последнюю свечу и уже рассчитанные индикаторы.

    Тут мы НЕ считаем индикаторы заново.
    Они уже должны быть в таблице indicators.
    """

    query = text(
        """
        SELECT
            c.symbol,
            c.interval,
            c.open_time,
            c.open_price,
            c.high_price,
            c.low_price,
            c.close_price,
            c.volume,
            i.ema_20,
            i.ema_50,
            i.ema_200,
            i.rsi_14,
            i.macd_line,
            i.macd_signal,
            i.macd_hist,
            i.atr_14,
            i.volume_sma_20
        FROM candles c
        JOIN indicators i
          ON i.symbol = c.symbol
         AND i.interval = c.interval
         AND i.open_time = c.open_time
        WHERE c.symbol = :symbol
          AND c.interval = :interval
        ORDER BY c.open_time DESC
        LIMIT 1
        """
    )

    df = pd.read_sql(
        query,
        engine,
        params={
            "symbol": symbol,
            "interval": interval,
        },
    )

    if df.empty:
        return None

    return df.iloc[0].to_dict()


def get_latest_ticker(engine, symbol: str) -> Optional[dict]:
    """
    Берём последний ticker snapshot.

    В таблице tickers время называется ts.
    Поэтому сортируем по ts DESC.
    """

    query = text(
        """
        SELECT
            symbol,
            ts,
            last_price,
            mark_price,
            index_price,
            funding_rate,
            open_interest
        FROM tickers
        WHERE symbol = :symbol
        ORDER BY ts DESC
        LIMIT 1
        """
    )

    df = pd.read_sql(
        query,
        engine,
        params={"symbol": symbol},
    )

    if df.empty:
        return None

    return df.iloc[0].to_dict()


def get_latest_funding_rate(engine, symbol: str) -> Optional[float]:
    """
    Берём последний funding rate из таблицы funding_rates.
    """

    query = text(
        """
        SELECT
            funding_time,
            funding_rate
        FROM funding_rates
        WHERE symbol = :symbol
        ORDER BY funding_time DESC
        LIMIT 1
        """
    )

    df = pd.read_sql(
        query,
        engine,
        params={"symbol": symbol},
    )

    if df.empty:
        return None

    return safe_float(df.iloc[0]["funding_rate"])


def get_open_interest_history(engine, symbol: str, candle_interval: str) -> pd.DataFrame:
    """
    Берём историю open interest.

    Важно:
    candles interval = 60
    open_interest interval = 1h
    """

    oi_interval = normalize_open_interest_interval(candle_interval)

    query = text(
        """
        SELECT
            ts,
            open_interest
        FROM open_interest
        WHERE symbol = :symbol
          AND interval = :interval
        ORDER BY ts DESC
        LIMIT 25
        """
    )

    return pd.read_sql(
        query,
        engine,
        params={
            "symbol": symbol,
            "interval": oi_interval,
        },
    )
