from __future__ import annotations

import pandas as pd

from app.analytics import market_analysis


def test_build_analysis_returns_stable_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        market_analysis,
        "get_latest_market_row",
        lambda engine, symbol, interval: {
            "open_time": "2026-07-19 15:00:00+00:00",
            "close_price": 65000,
            "ema_20": 64500,
            "ema_50": 64000,
            "ema_200": 63000,
            "rsi_14": 58.5,
            "macd_line": 12,
            "macd_signal": 8,
            "macd_hist": 4,
            "atr_14": 420,
            "volume": 1200,
            "volume_sma_20": 1000,
        },
    )
    monkeypatch.setattr(
        market_analysis,
        "get_latest_ticker",
        lambda engine, symbol: {
            "last_price": 65100,
            "mark_price": 65090,
            "index_price": 65080,
            "funding_rate": 0.0001,
            "open_interest": 123456,
        },
    )
    monkeypatch.setattr(
        market_analysis,
        "get_latest_funding_rate",
        lambda engine, symbol: 0.0002,
    )
    monkeypatch.setattr(
        market_analysis,
        "get_open_interest_history",
        lambda engine, symbol, interval: pd.DataFrame(
            {"open_interest": [110.0, 100.0]}
        ),
    )
    monkeypatch.setattr(
        market_analysis,
        "analyze_support_resistance",
        lambda symbol, interval, current_price, limit: {
            "support_resistance": {
                "support_levels": [64500],
                "resistance_levels": [66000],
                "method": "fixture",
                "candles_used": 240,
            },
            "scenarios": {
                "scenario_up": "Upside.",
                "scenario_down": "Downside.",
                "neutral_summary": "Neutral.",
            },
        },
    )

    analysis = market_analysis.build_analysis(
        engine=object(),
        symbol="BTCUSDT",
        interval="60",
    )

    required_keys = {
        "symbol",
        "interval",
        "candle_time",
        "price",
        "trend",
        "ema",
        "rsi",
        "macd",
        "atr",
        "volume",
        "funding",
        "open_interest",
        "support_resistance",
        "scenarios",
        "risk_note",
        "summary",
    }
    assert required_keys.issubset(analysis)
    assert analysis["symbol"] == "BTCUSDT"
    assert analysis["price"]["current"] == 65100
    assert "short_comment" in analysis["summary"]


def test_build_analysis_reports_missing_candles_and_indicators(monkeypatch) -> None:
    monkeypatch.setattr(
        market_analysis,
        "get_latest_market_row",
        lambda engine, symbol, interval: None,
    )

    analysis = market_analysis.build_analysis(
        engine=object(),
        symbol="ETHUSDT",
        interval="60",
    )

    assert analysis["symbol"] == "ETHUSDT"
    assert "error" in analysis
