"""
одуль итогового рыночного summary.

адача:
собрать общий человеческий вывод из уже рассчитанных блоков:
trend, RSI, MACD, volume, funding, open interest, support/resistance.
"""

from __future__ import annotations

from typing import Any


def get_nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data

    for key in keys:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def build_bias(trend_direction: str | None, volume_ratio: float | None) -> str:
    """
    ростая оценка общего уклона рынка.

    то не торговый сигнал, а текстовая классификация состояния.
    """

    if trend_direction in {"strong_bullish", "bullish"}:
        if volume_ratio is not None and volume_ratio >= 1:
            return "bullish"
        return "cautious_bullish"

    if trend_direction in {"strong_bearish", "bearish", "mixed_bearish"}:
        if volume_ratio is not None and volume_ratio >= 1:
            return "bearish"
        return "neutral_to_bearish"

    if trend_direction in {"mixed_bullish"}:
        return "neutral_to_bullish"

    return "neutral"


def build_market_state_comment(
    current_price: float | None,
    nearest_support: float | None,
    nearest_resistance: float | None,
    trend_comment: str | None,
) -> str:
    if current_price is None:
        return "едостаточно данных для общего вывода по рынку."

    if nearest_support is not None and nearest_resistance is not None:
        return (
            f"Цена находится между ближайшей поддержкой {nearest_support} "
            f"и ближайшим сопротивлением {nearest_resistance}. "
            f"{trend_comment or 'Трендовая структура требует дополнительного подтверждения.'}"
        )

    if nearest_support is not None:
        return (
            f"Цена находится выше ближайшей поддержки {nearest_support}. "
            f"{trend_comment or 'ажно следить за удержанием этой зоны.'}"
        )

    if nearest_resistance is not None:
        return (
            f"Цена находится ниже ближайшего сопротивления {nearest_resistance}. "
            f"{trend_comment or 'ажно следить за реакцией цены у этой зоны.'}"
        )

    return trend_comment or "ыночная структура пока недостаточно ясная."


def build_main_risk(
    volume_ratio: float | None,
    funding_percent: float | None,
    open_interest_change: float | None,
) -> str:
    risks: list[str] = []

    if volume_ratio is not None and volume_ratio < 0.7:
        risks.append("движение слабо подтверждается объёмом")

    if funding_percent is not None and abs(funding_percent) >= 0.03:
        risks.append("funding показывает заметный перекос позиций")

    if open_interest_change is not None and open_interest_change <= -3:
        risks.append("open interest снижается, часть позиций закрывается")

    if open_interest_change is not None and open_interest_change >= 3:
        risks.append("open interest растёт, в рынок заходят новые позиции")

    if not risks:
        return "Главный риск — ложный пробой ближайших уровней и резкий вынос ликвидности."

    return "ГГлавный риск: " + "; ".join(risks) + "."


def build_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    current_price = get_nested(analysis, "price", "current")
    trend_direction = get_nested(analysis, "trend", "direction")
    trend_comment = get_nested(analysis, "trend", "comment")

    volume_ratio = get_nested(analysis, "volume", "ratio")
    funding_percent = get_nested(analysis, "funding", "percent")
    open_interest_change = get_nested(analysis, "open_interest", "change_24h_percent")

    support_levels = get_nested(analysis, "support_resistance", "support_levels") or []
    resistance_levels = get_nested(analysis, "support_resistance", "resistance_levels") or []

    nearest_support = support_levels[0] if support_levels else None
    nearest_resistance = resistance_levels[0] if resistance_levels else None

    bias = build_bias(
        trend_direction=trend_direction,
        volume_ratio=volume_ratio,
    )

    short_comment = build_market_state_comment(
        current_price=current_price,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        trend_comment=trend_comment,
    )

    main_risk = build_main_risk(
        volume_ratio=volume_ratio,
        funding_percent=funding_percent,
        open_interest_change=open_interest_change,
    )

    return {
        "market_state": trend_direction or "unknown",
        "bias": bias,
        "short_comment": short_comment,
        "main_risk": main_risk,
    }
