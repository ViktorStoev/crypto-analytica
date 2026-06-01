from app.analytics.data_loader import get_database_url
from app.analytics.data_loader import get_latest_funding_rate
from app.analytics.data_loader import get_latest_market_row
from app.analytics.data_loader import get_latest_ticker
from app.analytics.data_loader import get_open_interest_history
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


def build_analysis(engine, symbol: str, interval: str) -> dict:
    latest = get_latest_market_row(engine, symbol, interval)

    if latest is None:
        return {
            "symbol": symbol,
            "interval": interval,
            "error": "\u041dет данных candles + indicators. \u0421начала запусти calculate_indicators.py.",
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

    # ля текущей цены берём ticker last_price, если он есть.
    # сли ticker недоступен, используем close_price последней свечи.
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

    # сли funding_rates почему-то пустая, пробуем взять funding из ticker.
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
                "scenario_up": "\u041dедостаточно данных для сценария роста.",
                "scenario_down": "\u041dедостаточно данных для сценария снижения.",
                "neutral_summary": "\u041dедостаточно данных для нейтрального сценария.",
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
            "comment": "\u042dто open interest из последнего ticker snapshot. \u0414ля динамики используется история из таблицы open_interest.",
        },
        "support_resistance": support_resistance_analysis["support_resistance"],
        "scenarios": support_resistance_analysis["scenarios"],
        "risk_note": "\u042dто аналитический обзор по данным Bybit, а не финансовая рекомендация. \u0412озможны ложные пробои, резкие выносы ликвидности и манипуляции.",
    }

    analysis["summary"] = build_summary(analysis)

    return analysis
