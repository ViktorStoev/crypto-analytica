"""
Аналитика импульса.

Сюда вынесены RSI, MACD и ATR.
"""

from __future__ import annotations

from typing import Optional

from app.analytics.utils import round_or_none
from app.analytics.utils import safe_float


def interpret_rsi(rsi: Optional[float]) -> dict:
    if rsi is None:
        return {
            "value": None,
            "comment": "RSI пока недоступен.",
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
        "comment": comment,
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
            "comment": "MACD пока недоступен.",
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
        "comment": comment,
    }


def interpret_atr(atr_14) -> dict:
    return {
        "atr_14": round_or_none(atr_14, 2),
        "comment": "ATR показывает средний диапазон движения цены за последние свечи.",
    }
