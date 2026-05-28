import os
import sys
import json
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text


def get_database_url() -> str:
    """
    Берём DATABASE_URL из .env.
    Если DATABASE_URL обычный postgresql://..., адаптируем его под SQLAlchemy + psycopg3.
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


def safe_float(value) -> Optional[float]:
    if value is None:
        return None

    if pd.isna(value):
        return None

    return float(value)


def get_latest_market_row(engine, symbol: str, interval: str) -> Optional[dict]:
    query = text("""
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
    """)

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
    Берём последний ticker.
    Тут предполагаем, что в таблице tickers есть created_at.
    Если у тебя колонка называется collected_at или snapshot_time,
    замени ORDER BY created_at DESC на своё имя колонки.
    """
    query = text("""
        SELECT
            symbol,
            last_price,
            mark_price,
            index_price,
            funding_rate,
            open_interest,
            created_at
        FROM tickers
        WHERE symbol = :symbol
        ORDER BY created_at DESC
        LIMIT 1
    """)

    try:
        df = pd.read_sql(query, engine, params={"symbol": symbol})
    except Exception:
        return None

    if df.empty:
        return None

    return df.iloc[0].to_dict()


def get_open_interest_history(engine, symbol: str, interval: str) -> pd.DataFrame:
    query = text("""
        SELECT
            open_time,
            open_interest
        FROM open_interest
        WHERE symbol = :symbol
          AND interval = :interval
        ORDER BY open_time DESC
        LIMIT 25
    """)

    try:
        return pd.read_sql(
            query,
            engine,
            params={
                "symbol": symbol,
                "interval": interval,
            },
        )
    except Exception:
        return pd.DataFrame()


def get_latest_funding_rate(engine, symbol: str) -> Optional[float]:
    """
    Основной вариант — берём funding_rate из funding_rates.
    Если не получилось — можно будет использовать funding_rate из tickers.
    """
    query = text("""
        SELECT funding_rate
        FROM funding_rates
        WHERE symbol = :symbol
        ORDER BY funding_time DESC
        LIMIT 1
    """)

    try:
        df = pd.read_sql(query, engine, params={"symbol": symbol})
    except Exception:
        return None

    if df.empty:
        return None

    return safe_float(df.iloc[0]["funding_rate"])


def interpret_trend(price, ema_20, ema_50, ema_200) -> dict:
    if None in [price, ema_20, ema_50, ema_200]:
        return {
            "direction": "unknown",
            "comment": "Недостаточно данных для определения тренда."
        }

    if price > ema_20 > ema_50 > ema_200:
        return {
            "direction": "bullish",
            "comment": "Цена выше EMA 20/50/200, структура тренда выглядит восходящей."
        }

    if price < ema_20 < ema_50 < ema_200:
        return {
            "direction": "bearish",
            "comment": "Цена ниже EMA 20/50/200, структура тренда выглядит нисходящей."
        }

    if price > ema_200:
        return {
            "direction": "mixed_bullish",
            "comment": "Цена выше EMA 200, но EMA 20/50/200 не выстроены идеально. Тренд скорее смешанный с бычьим уклоном."
        }

    if price < ema_200:
        return {
            "direction": "mixed_bearish",
            "comment": "Цена ниже EMA 200, но EMA 20/50/200 не выстроены идеально. Тренд скорее смешанный с медвежьим уклоном."
        }

    return {
        "direction": "neutral",
        "comment": "Цена находится около ключевых средних, выраженного направления нет."
    }


def interpret_rsi(rsi: Optional[float]) -> dict:
    if rsi is None:
        return {
            "value": None,
            "comment": "RSI пока недоступен."
        }

    if rsi >= 70:
        comment = "RSI выше 70 — рынок может быть перегрет вверх."
    elif rsi <= 30:
        comment = "RSI ниже 30 — рынок может быть перепродан."
    elif rsi >= 55:
        comment = "RSI выше нейтральной зоны — импульс умеренно сильный."
    elif rsi <= 45:
        comment = "RSI ниже нейтральной зоны — импульс ослаблен."
    else:
        comment = "RSI около нейтральной зоны, явного перекоса нет."

    return {
        "value": round(rsi, 2),
        "comment": comment
    }


def interpret_volume(volume: Optional[float], volume_sma_20: Optional[float]) -> dict:
    if volume is None or volume_sma_20 is None or volume_sma_20 == 0:
        return {
            "current": volume,
            "sma_20": volume_sma_20,
            "ratio": None,
            "comment": "Недостаточно данных для оценки объёма."
        }

    ratio = volume / volume_sma_20

    if ratio >= 1.8:
        comment = "Текущий объём значительно выше среднего — движение подтверждается повышенной активностью."
    elif ratio >= 1.2:
        comment = "Текущий объём выше среднего — активность на рынке повышена."
    elif ratio <= 0.7:
        comment = "Текущий объём ниже среднего — движение пока слабее подтверждается объёмом."
    else:
        comment = "Текущий объём около среднего значения."

    return {
        "current": round(volume, 4),
        "sma_20": round(volume_sma_20, 4),
        "ratio": round(ratio, 2),
        "comment": comment
    }


def interpret_funding(funding_rate: Optional[float]) -> dict:
    if funding_rate is None:
        return {
            "value": None,
            "percent": None,
            "comment": "Funding rate недоступен."
        }

    funding_percent = funding_rate * 100

    if funding_rate >= 0.0005:
        comment = "Funding заметно положительный — лонги платят шортам, возможен перегрев лонгов."
    elif funding_rate > 0.0001:
        comment = "Funding положительный — настроение скорее бычье, но без явного экстремума."
    elif funding_rate <= -0.0005:
        comment = "Funding заметно отрицательный — шорты платят лонгам, возможен перегрев шортов."
    elif funding_rate < -0.0001:
        comment = "Funding отрицательный — настроение скорее осторожное или медвежье."
    else:
        comment = "Funding около нуля — сильного перекоса между лонгами и шортами не видно."

    return {
        "value": funding_rate,
        "percent": round(funding_percent, 4),
        "comment": comment
    }


def interpret_open_interest(oi_df: pd.DataFrame) -> dict:
    if oi_df.empty or len(oi_df) < 2:
        return {
            "value": None,
            "change_24h_percent": None,
            "comment": "Недостаточно данных для оценки open interest."
        }

    oi_df = oi_df.copy()
    oi_df["open_interest"] = pd.to_numeric(oi_df["open_interest"], errors="coerce")

    latest_oi = oi_df.iloc[0]["open_interest"]

    # Так как interval=60, 24 строки назад примерно равно 24 часам.
    if len(oi_df) >= 25:
        previous_oi = oi_df.iloc[24]["open_interest"]
    else:
        previous_oi = oi_df.iloc[-1]["open_interest"]

    if pd.isna(latest_oi) or pd.isna(previous_oi) or previous_oi == 0:
        return {
            "value": safe_float(latest_oi),
            "change_24h_percent": None,
            "comment": "Open interest есть, но изменение посчитать не удалось."
        }

    change_percent = ((latest_oi - previous_oi) / previous_oi) * 100

    if change_percent >= 3:
        comment = "Open interest заметно растёт — в рынок заходят новые позиции."
    elif change_percent <= -3:
        comment = "Open interest заметно снижается — часть позиций закрывается."
    else:
        comment = "Open interest меняется слабо — сильного притока или выхода позиций не видно."

    return {
        "value": round(float(latest_oi), 4),
        "change_24h_percent": round(float(change_percent), 2),
        "comment": comment
    }


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python scripts/analyze_symbol.py BTCUSDT 60")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    interval = sys.argv[2]

    engine = create_engine(get_database_url())

    latest = get_latest_market_row(engine, symbol, interval)

    if latest is None:
        print(json.dumps({
            "symbol": symbol,
            "interval": interval,
            "error": "No candle + indicator data found. Run calculate_indicators.py first."
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    ticker = get_latest_ticker(engine, symbol)
    oi_history = get_open_interest_history(engine, symbol, interval)

    price = safe_float(latest["close_price"])
    ema_20 = safe_float(latest["ema_20"])
    ema_50 = safe_float(latest["ema_50"])
    ema_200 = safe_float(latest["ema_200"])
    rsi_14 = safe_float(latest["rsi_14"])
    volume = safe_float(latest["volume"])
    volume_sma_20 = safe_float(latest["volume_sma_20"])

    funding_rate = get_latest_funding_rate(engine, symbol)

    if funding_rate is None and ticker is not None:
        funding_rate = safe_float(ticker.get("funding_rate"))

    analysis = {
        "symbol": symbol,
        "interval": interval,
        "open_time": str(latest["open_time"]),
        "price": price,

        "trend": interpret_trend(
            price=price,
            ema_20=ema_20,
            ema_50=ema_50,
            ema_200=ema_200,
        ),

        "rsi": interpret_rsi(rsi_14),

        "ema": {
            "ema_20": None if ema_20 is None else round(ema_20, 2),
            "ema_50": None if ema_50 is None else round(ema_50, 2),
            "ema_200": None if ema_200 is None else round(ema_200, 2),
        },

        "macd": {
            "line": None if safe_float(latest["macd_line"]) is None else round(safe_float(latest["macd_line"]), 4),
            "signal": None if safe_float(latest["macd_signal"]) is None else round(safe_float(latest["macd_signal"]), 4),
            "hist": None if safe_float(latest["macd_hist"]) is None else round(safe_float(latest["macd_hist"]), 4),
        },

        "atr": {
            "atr_14": None if safe_float(latest["atr_14"]) is None else round(safe_float(latest["atr_14"]), 2),
            "comment": "ATR показывает средний диапазон движения цены за последние свечи."
        },

        "volume": interpret_volume(
            volume=volume,
            volume_sma_20=volume_sma_20,
        ),

        "funding": interpret_funding(funding_rate),

        "open_interest": interpret_open_interest(oi_history),
    }

    print(json.dumps(analysis, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()