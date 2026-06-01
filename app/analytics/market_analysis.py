import os
from typing import Optional

import pandas as pd
from sqlalchemy import text

from app.analytics.derivatives import interpret_funding
from app.analytics.derivatives import interpret_open_interest
from app.analytics.momentum import interpret_atr
from app.analytics.momentum import interpret_macd
from app.analytics.momentum import interpret_rsi
from app.analytics.support_resistance import analyze_support_resistance
from app.analytics.summary import build_summary
from app.analytics.trend import interpret_trend
from app.analytics.utils import round_or_none
from app.analytics.utils import safe_float
from app.analytics.volume import interpret_volume


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


def build_analysis(engine, symbol: str, interval: str) -> dict:
    latest = get_latest_market_row(engine, symbol, interval)

    if latest is None:
        return {
            "symbol": symbol,
            "interval": interval,
            "error": "Нет данных candles + indicators. Сначала запусти calculate_indicators.py.",
        }

    ticker = get_latest_ticker(engine, symbol)
    oi_history = get_open_interest_history(engine, symbol, interval)

    candle_close_price = safe_float(latest["close_price"])

    ticker_last_price = None
    ticker_mark_price = None
    ticker_index_price = None
    ticker_open_interest = None

    if ticker is not None:
        ticker_last_price = safe_float(ticker.get("last_price"))
        ticker_mark_price = safe_float(ticker.get("mark_price"))
        ticker_index_price = safe_float(ticker.get("index_price"))
        ticker_open_interest = safe_float(ticker.get("open_interest"))

    # Для текущей цены берём ticker last_price, если он есть.
    # Если ticker недоступен, используем close_price последней свечи.
    current_price = (
        ticker_last_price
        if ticker_last_price is not None
        else candle_close_price
    )

    ema_20 = safe_float(latest["ema_20"])
    ema_50 = safe_float(latest["ema_50"])
    ema_200 = safe_float(latest["ema_200"])
    rsi_14 = safe_float(latest["rsi_14"])
    volume = safe_float(latest["volume"])
    volume_sma_20 = safe_float(latest["volume_sma_20"])

    funding_rate = get_latest_funding_rate(engine, symbol)

    # Если funding_rates почему-то пустая, пробуем взять funding из ticker.
    if funding_rate is None and ticker is not None:
        funding_rate = safe_float(ticker.get("funding_rate"))

    if current_price is not None:
        support_resistance_analysis = analyze_support_resistance(
            symbol=symbol,
            interval=interval,
            current_price=current_price,
            limit=240,
        )
    else:
        support_resistance_analysis = {
            "support_resistance": {
                "support_levels": [],
                "resistance_levels": [],
                "method": "no_current_price",
                "candles_used": 0,
            },
            "scenarios": {
                "scenario_up": "Недостаточно данных для сценария роста.",
                "scenario_down": "Недостаточно данных для сценария снижения.",
                "neutral_summary": "Недостаточно данных для нейтрального сценария.",
            },
        }

    analysis = {
        "symbol": symbol,
        "interval": interval,
        "candle_time": str(latest["open_time"]),
        "price": {
            "current": round_or_none(current_price, 2),
            "last_candle_close": round_or_none(candle_close_price, 2),
            "mark_price": round_or_none(ticker_mark_price, 2),
            "index_price": round_or_none(ticker_index_price, 2),
        },
        "trend": interpret_trend(
            price=current_price,
            ema_20=ema_20,
            ema_50=ema_50,
            ema_200=ema_200,
        ),
        "ema": {
            "ema_20": round_or_none(ema_20, 2),
            "ema_50": round_or_none(ema_50, 2),
            "ema_200": round_or_none(ema_200, 2),
        },
        "rsi": interpret_rsi(rsi_14),
        "macd": interpret_macd(
            macd_line=latest["macd_line"],
            macd_signal=latest["macd_signal"],
            macd_hist=latest["macd_hist"],
        ),
        "atr": interpret_atr(latest["atr_14"]),
        "volume": interpret_volume(
            volume=volume,
            volume_sma_20=volume_sma_20,
        ),
        "funding": interpret_funding(funding_rate),
        "open_interest": interpret_open_interest(oi_history),
        "ticker_open_interest": {
            "value": round_or_none(ticker_open_interest, 4),
            "comment": "Это open interest из последнего ticker snapshot. Для динамики используется история из таблицы open_interest.",
        },
        "support_resistance": support_resistance_analysis["support_resistance"],
        "scenarios": support_resistance_analysis["scenarios"],
        "risk_note": "Это аналитический обзор по данным Bybit, а не финансовая рекомендация. Возможны ложные пробои, резкие выносы ликвидности и манипуляции.",
    }

    analysis["summary"] = build_summary(analysis)

    return analysis
