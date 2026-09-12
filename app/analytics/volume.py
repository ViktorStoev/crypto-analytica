"""
Аналитика объёма.
"""

from __future__ import annotations

from typing import Optional


def interpret_volume(volume: Optional[float], volume_sma_20: Optional[float]) -> dict:
    if volume is None or volume_sma_20 is None or volume_sma_20 == 0:
        return {
            "current": volume,
            "sma_20": volume_sma_20,
            "ratio": None,
            "comment": "Недостаточно данных для оценки объёма.",
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
        "comment": comment,
    }
