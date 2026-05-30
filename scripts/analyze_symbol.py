import os
import sys
import json
from decimal import Decimal
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text


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


def safe_float(value) -> Optional[float]:
    """
    Аккуратно переводит значения из PostgreSQL / pandas в float.

    Почему это нужно:
    PostgreSQL numeric часто приходит как Decimal,
    а пустые значения могут приходить как None или NaN.
    """
    if value is None:
        return None

    if pd.isna(value):
        return None

    if isinstance(value, Decimal):
        return float(value)

    return float(value)


def round_or_none(value, digits: int = 2):
    value = safe_float(value)

    if value is None:
        return None

    return round(value, digits)


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
    Берём последний ticker snapshot.

    В твоей таблице tickers время называется ts.
    Поэтому сортируем по ts DESC.
    """
    query = text("""
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
    """)

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
    query = text("""
        SELECT
            funding_time,
            funding_rate
        FROM funding_rates
        WHERE symbol = :symbol
        ORDER BY funding_time DESC
        LIMIT 1
    """)

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

    query = text("""
        SELECT
            ts,
            open_interest
        FROM open_interest
        WHERE symbol = :symbol
          AND interval = :interval
        ORDER BY ts DESC
        LIMIT 25
    """)

    return pd.read_sql(
        query,
        engine,
        params={
            "symbol": symbol,
            "interval": oi_interval,
        },
    )


def interpret_trend(price, ema_20, ema_50, ema_200) -> dict:
    """
    Простая оценка тренда по цене и EMA.

    Это не торговый сигнал.
    Это только текстовое описание структуры рынка.
    """
    if None in [price, ema_20, ema_50, ema_200]:
        return {
            "direction": "unknown",
            "comment": "Недостаточно данных для определения тренда."
        }

    if price > ema_20 > ema_50 > ema_200:
        return {
            "direction": "bullish",
            "comment": "Цена выше EMA 20/50/200, структура выглядит восходящей."
        }

    if price < ema_20 < ema_50 < ema_200:
        return {
            "direction": "bearish",
            "comment": "Цена ниже EMA 20/50/200, структура выглядит нисходящей."
        }

    if price > ema_200:
        return {
            "direction": "mixed_bullish",
            "comment": "Цена выше EMA 200, но средние не выстроены идеально. Картина смешанная с бычьим уклоном."
        }

    if price < ema_200:
        return {
            "direction": "mixed_bearish",
            "comment": "Цена ниже EMA 200, но средние не выстроены идеально. Картина смешанная с медвежьим уклоном."
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


def interpret_macd(macd_line, macd_signal, macd_hist) -> dict:
    macd_line = safe_float(macd_line)
    macd_signal = safe_float(macd_signal)
    macd_hist = safe_float(macd_hist)

    if None in [macd_line, macd_signal, macd_hist]:
        return {
            "line": None,
            "signal": None,
            "hist": None,
            "comment": "MACD пока недоступен."
        }

    if macd_line > macd_signal and macd_hist > 0:
        comment = "MACD выше сигнальной линии, импульс улучшается."
    elif macd_line < macd_signal and macd_hist < 0:
        comment = "MACD ниже сигнальной линии, импульс ослабевает."
    else:
        comment = "MACD показывает смешанную картину, сильного подтверждения импульса нет."

    return {
        "line": round(macd_line, 4),
        "signal": round(macd_signal, 4),
        "hist": round(macd_hist, 4),
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
        comment = "Текущий объём значительно выше среднего — активность заметно повышена."
    elif ratio >= 1.2:
        comment = "Текущий объём выше среднего — движение частично подтверждается объёмом."
    elif ratio <= 0.7:
        comment = "Текущий объём ниже среднего — движение пока слабо подтверждается объёмом."
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
    """
    Смотрим изменение open interest примерно за 24 часа.

    Так как сейчас анализируем 1h open interest,
    24 строки назад — это примерно сутки назад.
    """
    if oi_df.empty or len(oi_df) < 2:
        return {
            "value": None,
            "change_24h_percent": None,
            "comment": "Недостаточно данных для оценки open interest."
        }

    oi_df = oi_df.copy()
    oi_df["open_interest"] = pd.to_numeric(oi_df["open_interest"], errors="coerce")

    latest_oi = oi_df.iloc[0]["open_interest"]

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


def build_analysis(engine, symbol: str, interval: str) -> dict:
    latest = get_latest_market_row(engine, symbol, interval)

    if latest is None:
        return {
            "symbol": symbol,
            "interval": interval,
            "error": "Нет данных candles + indicators. Сначала запусти calculate_indicators.py."
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
    current_price = ticker_last_price if ticker_last_price is not None else candle_close_price

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

        "atr": {
            "atr_14": round_or_none(latest["atr_14"], 2),
            "comment": "ATR показывает средний диапазон движения цены за последние свечи."
        },

        "volume": interpret_volume(
            volume=volume,
            volume_sma_20=volume_sma_20,
        ),

        "funding": interpret_funding(funding_rate),

        "open_interest": interpret_open_interest(oi_history),

        "ticker_open_interest": {
            "value": round_or_none(ticker_open_interest, 4),
            "comment": "Это open interest из последнего ticker snapshot. Для динамики используется история из таблицы open_interest."
        },

        "risk_note": "Это аналитический обзор по данным Bybit, а не финансовая рекомендация. Возможны ложные пробои, резкие выносы ликвидности и манипуляции."
    }

    return analysis


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python scripts/analyze_symbol.py BTCUSDT 60")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    interval = sys.argv[2]

    engine = create_engine(get_database_url())

    analysis = build_analysis(
        engine=engine,
        symbol=symbol,
        interval=interval,
    )

    print(json.dumps(analysis, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()