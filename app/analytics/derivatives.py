"""
Аналитика деривативов.

Сюда вынесены:
- funding rate
- open interest
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from app.analytics.utils import safe_float


def interpret_funding(funding_rate: Optional[float]) -> dict:
    if funding_rate is None:
        return {
            "value": None,
            "percent": None,
            "comment": "Funding rate недоступен.",
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
        "comment": comment,
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
            "comment": "Недостаточно данных для оценки open interest.",
        }

    oi_df = oi_df.copy()
    oi_df["open_interest"] = pd.to_numeric(
        oi_df["open_interest"],
        errors="coerce",
    )

    latest_oi = oi_df.iloc[0]["open_interest"]

    if len(oi_df) >= 25:
        previous_oi = oi_df.iloc[24]["open_interest"]
    else:
        previous_oi = oi_df.iloc[-1]["open_interest"]

    if pd.isna(latest_oi) or pd.isna(previous_oi) or previous_oi == 0:
        return {
            "value": safe_float(latest_oi),
            "change_24h_percent": None,
            "comment": "Open interest есть, но изменение посчитать не удалось.",
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
        "comment": comment,
    }
