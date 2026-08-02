from __future__ import annotations

from copy import deepcopy

import pytest


def make_analysis(
    *,
    symbol: str = "BTCUSDT",
    price: float = 65000.0,
    rsi: float = 58.2,
    trend_direction: str = "bullish",
) -> dict:
    base_symbol = symbol.replace("USDT", "")

    return {
        "symbol": symbol,
        "interval": "60",
        "candle_time": "2026-07-19 15:00:00+00:00",
        "price": {
            "current": price,
            "last_candle_close": price - 25,
            "mark_price": price,
            "index_price": price - 10,
        },
        "trend": {
            "direction": trend_direction,
            "comment": f"{base_symbol} trend comment.",
        },
        "ema": {
            "ema_20": price - 100,
            "ema_50": price - 300,
            "ema_200": price - 900,
        },
        "rsi": {
            "value": rsi,
            "comment": f"{base_symbol} RSI comment.",
        },
        "macd": {
            "line": 12.1,
            "signal": 8.2,
            "hist": 3.9,
            "comment": f"{base_symbol} MACD comment.",
        },
        "atr": {
            "atr_14": 420.0,
            "comment": "ATR comment.",
        },
        "volume": {
            "current": 1000.0,
            "sma_20": 800.0,
            "ratio": 1.25,
            "comment": f"{base_symbol} volume comment.",
        },
        "funding": {
            "value": 0.0001,
            "percent": 0.01,
            "comment": f"{base_symbol} funding comment.",
        },
        "open_interest": {
            "value": 123456.0,
            "change_24h_percent": 1.4,
            "comment": f"{base_symbol} OI comment.",
        },
        "ticker_open_interest": {
            "value": 123456.0,
            "comment": "Ticker OI comment.",
        },
        "support_resistance": {
            "support_levels": [price - 500, price - 1000],
            "resistance_levels": [price + 500, price + 1000],
            "method": "fixture",
            "candles_used": 240,
        },
        "scenarios": {
            "scenario_up": f"{base_symbol} upside scenario.",
            "scenario_down": f"{base_symbol} downside scenario.",
            "neutral_summary": f"{base_symbol} neutral scenario.",
        },
        "risk_note": "Not financial advice.",
        "summary": {
            "market_state": trend_direction,
            "bias": "bullish",
            "short_comment": f"{base_symbol} short summary.",
            "main_risk": f"{base_symbol} main risk.",
        },
    }


@pytest.fixture
def analysis_fixture() -> dict:
    return make_analysis()


@pytest.fixture
def daily_summary_analyses() -> list[dict]:
    btc = make_analysis(symbol="BTCUSDT", price=65000.0, rsi=58.2)
    eth = make_analysis(symbol="ETHUSDT", price=3500.0, rsi=49.1)
    sol = make_analysis(symbol="SOLUSDT", price=180.0, rsi=63.4)

    return [deepcopy(btc), deepcopy(eth), deepcopy(sol)]
