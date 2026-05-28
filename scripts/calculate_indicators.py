import os
import sys
import json
import numpy as np
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


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI показывает, насколько движение цены перегрето вверх или вниз.

    Примерно:
    - RSI выше 70 — возможный перегрев вверх;
    - RSI ниже 30 — возможная перепроданность;
    - RSI около 50 — нейтральная зона.
    """
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ATR показывает средний диапазон движения свечи.
    Проще: насколько сильно в среднем ходит цена.
    """
    previous_close = df["close_price"].shift(1)

    high_low = df["high_price"] - df["low_price"]
    high_prev_close = (df["high_price"] - previous_close).abs()
    low_prev_close = (df["low_price"] - previous_close).abs()

    true_range = pd.concat(
        [high_low, high_prev_close, low_prev_close],
        axis=1
    ).max(axis=1)

    atr = true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    return atr


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Основной расчёт индикаторов.
    На входе свечи.
    На выходе датафрейм с EMA, RSI, MACD, ATR и средним объёмом.
    """
    df = df.copy()

    numeric_columns = [
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    close = df["close_price"]

    # EMA
    df["ema_20"] = close.ewm(span=20, adjust=False, min_periods=20).mean()
    df["ema_50"] = close.ewm(span=50, adjust=False, min_periods=50).mean()
    df["ema_200"] = close.ewm(span=200, adjust=False, min_periods=200).mean()

    # RSI
    df["rsi_14"] = calculate_rsi(close, period=14)

    # MACD: стандартная формула 12 / 26 / 9
    ema_12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema_26 = close.ewm(span=26, adjust=False, min_periods=26).mean()

    df["macd_line"] = ema_12 - ema_26
    df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False, min_periods=9).mean()
    df["macd_hist"] = df["macd_line"] - df["macd_signal"]

    # ATR
    df["atr_14"] = calculate_atr(df, period=14)

    # Средний объём за 20 свечей
    df["volume_sma_20"] = df["volume"].rolling(window=20, min_periods=20).mean()

    return df


def load_candles(engine, symbol: str, interval: str) -> pd.DataFrame:
    query = text("""
        SELECT
            symbol,
            interval,
            open_time,
            open_price,
            high_price,
            low_price,
            close_price,
            volume
        FROM candles
        WHERE symbol = :symbol
          AND interval = :interval
        ORDER BY open_time ASC
    """)

    return pd.read_sql(
        query,
        engine,
        params={
            "symbol": symbol,
            "interval": interval,
        },
    )


def save_indicators(engine, df: pd.DataFrame) -> int:
    columns = [
        "symbol",
        "interval",
        "open_time",
        "ema_20",
        "ema_50",
        "ema_200",
        "rsi_14",
        "macd_line",
        "macd_signal",
        "macd_hist",
        "atr_14",
        "volume_sma_20",
    ]

    result_df = df[columns].copy()

    # Чтобы NaN нормально записывались в PostgreSQL как NULL
    result_df = result_df.replace({np.nan: None})

    records = result_df.to_dict(orient="records")

    if not records:
        return 0

    insert_query = text("""
        INSERT INTO indicators (
            symbol,
            interval,
            open_time,
            ema_20,
            ema_50,
            ema_200,
            rsi_14,
            macd_line,
            macd_signal,
            macd_hist,
            atr_14,
            volume_sma_20
        )
        VALUES (
            :symbol,
            :interval,
            :open_time,
            :ema_20,
            :ema_50,
            :ema_200,
            :rsi_14,
            :macd_line,
            :macd_signal,
            :macd_hist,
            :atr_14,
            :volume_sma_20
        )
        ON CONFLICT (symbol, interval, open_time)
        DO UPDATE SET
            ema_20 = EXCLUDED.ema_20,
            ema_50 = EXCLUDED.ema_50,
            ema_200 = EXCLUDED.ema_200,
            rsi_14 = EXCLUDED.rsi_14,
            macd_line = EXCLUDED.macd_line,
            macd_signal = EXCLUDED.macd_signal,
            macd_hist = EXCLUDED.macd_hist,
            atr_14 = EXCLUDED.atr_14,
            volume_sma_20 = EXCLUDED.volume_sma_20,
            updated_at = now()
    """)

    with engine.begin() as connection:
        connection.execute(insert_query, records)

    return len(records)


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python scripts/calculate_indicators.py BTCUSDT 60")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    interval = sys.argv[2]

    engine = create_engine(get_database_url())

    print(f"Calculating indicators for {symbol}, interval={interval}")

    candles = load_candles(engine, symbol, interval)

    if candles.empty:
        print(f"No candles found for {symbol} interval={interval}")
        sys.exit(1)

    print(f"Loaded candles: {len(candles)}")
    print(f"From: {candles['open_time'].min()}")
    print(f"To:   {candles['open_time'].max()}")

    indicators = calculate_indicators(candles)

    saved_count = save_indicators(engine, indicators)

    latest_row = indicators.iloc[-1]

    summary = {
        "symbol": symbol,
        "interval": interval,
        "candles_loaded": len(candles),
        "indicators_saved": saved_count,
        "latest_open_time": str(latest_row["open_time"]),
        "latest_close_price": float(latest_row["close_price"]),
        "latest_ema_20": None if pd.isna(latest_row["ema_20"]) else float(latest_row["ema_20"]),
        "latest_ema_50": None if pd.isna(latest_row["ema_50"]) else float(latest_row["ema_50"]),
        "latest_ema_200": None if pd.isna(latest_row["ema_200"]) else float(latest_row["ema_200"]),
        "latest_rsi_14": None if pd.isna(latest_row["rsi_14"]) else float(latest_row["rsi_14"]),
        "latest_macd_line": None if pd.isna(latest_row["macd_line"]) else float(latest_row["macd_line"]),
        "latest_macd_signal": None if pd.isna(latest_row["macd_signal"]) else float(latest_row["macd_signal"]),
        "latest_macd_hist": None if pd.isna(latest_row["macd_hist"]) else float(latest_row["macd_hist"]),
        "latest_atr_14": None if pd.isna(latest_row["atr_14"]) else float(latest_row["atr_14"]),
        "latest_volume_sma_20": None if pd.isna(latest_row["volume_sma_20"]) else float(latest_row["volume_sma_20"]),
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()