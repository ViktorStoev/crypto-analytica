from __future__ import annotations

import pandas as pd
import pytest

from app.analytics.derivatives import interpret_funding, interpret_open_interest
from app.analytics.momentum import interpret_macd, interpret_rsi
from app.analytics.support_resistance import find_support_resistance_levels
from app.analytics.trend import interpret_trend
from app.analytics.volume import interpret_volume
from scripts.calculate_indicators import calculate_indicators


def test_calculate_indicators_adds_expected_columns() -> None:
    candles = pd.DataFrame(
        {
            "symbol": ["BTCUSDT"] * 220,
            "interval": ["60"] * 220,
            "open_time": pd.date_range("2026-01-01", periods=220, freq="h"),
            "open_price": range(100, 320),
            "high_price": range(101, 321),
            "low_price": range(99, 319),
            "close_price": range(100, 320),
            "volume": [1000 + index for index in range(220)],
        }
    )

    result = calculate_indicators(candles)

    expected_columns = {
        "ema_20",
        "ema_50",
        "ema_200",
        "rsi_14",
        "macd_line",
        "macd_signal",
        "macd_hist",
        "atr_14",
        "volume_sma_20",
    }
    assert expected_columns.issubset(result.columns)
    assert result.iloc[-1]["ema_200"] is not None
    assert not pd.isna(result.iloc[-1]["volume_sma_20"])


@pytest.mark.parametrize(
    ("price", "ema_20", "ema_50", "ema_200", "direction"),
    [
        (110, 105, 100, 95, "bullish"),
        (90, 95, 100, 105, "bearish"),
        (110, 100, 115, 95, "mixed_bullish"),
        (90, 100, 85, 95, "mixed_bearish"),
    ],
)
def test_interpret_trend_classifies_market_structure(
    price: float,
    ema_20: float,
    ema_50: float,
    ema_200: float,
    direction: str,
) -> None:
    assert interpret_trend(price, ema_20, ema_50, ema_200)["direction"] == direction


def test_interpret_momentum_volume_and_derivatives() -> None:
    assert interpret_rsi(72)["value"] == 72
    assert "comment" in interpret_macd(2, 1, 0.5)
    assert interpret_volume(180, 100)["ratio"] == 1.8
    assert interpret_funding(0.0005)["percent"] == 0.05

    oi_history = pd.DataFrame(
        {
            "open_interest": [130.0] + [100.0] * 24,
        }
    )
    assert interpret_open_interest(oi_history)["change_24h_percent"] == 30.0


def test_find_support_resistance_levels_uses_local_pivots() -> None:
    candles = [
        {"low": 10, "high": 20},
        {"low": 9, "high": 21},
        {"low": 8, "high": 25},
        {"low": 9, "high": 21},
        {"low": 10, "high": 20},
        {"low": 12, "high": 22},
        {"low": 11, "high": 24},
        {"low": 12, "high": 22},
        {"low": 13, "high": 21},
    ]

    result = find_support_resistance_levels(
        candles=candles,
        current_price=15,
        pivot_window=2,
        max_levels=2,
    )

    assert result["method"] == "local_pivots"
    assert 8 in result["support_levels"]
    assert 25 in result["resistance_levels"]
