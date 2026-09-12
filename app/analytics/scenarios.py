"""
Сценарии движения рынка.

тот модуль не ищет уровни сам.
н получает уже найденные support/resistance уровни
и формирует текстовые сценарии.
"""

from __future__ import annotations


def build_market_scenarios(
    current_price: float,
    support_levels: list[float],
    resistance_levels: list[float],
) -> dict[str, str]:
    nearest_support = support_levels[0] if support_levels else None
    nearest_resistance = resistance_levels[0] if resistance_levels else None

    if nearest_resistance is not None:
        scenario_up = (
            f"\u0415сли цена закрепится выше ближайшего сопротивления "
            f"{nearest_resistance}, рынок может попробовать продолжить движение "
            f"к следующей зоне сопротивления. \u041fодтверждением будет рост объёма "
            f"и удержание цены выше пробитого уровня."
        )
    else:
        scenario_up = (
            "\u0411лижайшее сопротивление не определено. "
            "\u0414ля сценария роста нужно дождаться формирования новой локальной зоны сверху."
        )

    if nearest_support is not None:
        scenario_down = (
            f"\u0415сли цена потеряет ближайшую поддержку {nearest_support}, "
            f"это может усилить давление продавцов. \u0412 таком случае рынок может "
            f"пойти к следующей зоне поддержки ниже."
        )
    else:
        scenario_down = (
            "\u0411лижайшая поддержка не определена. "
            "\u0414ля сценария снижения нужно дождаться формирования новой локальной зоны снизу."
        )

    if nearest_support is not None and nearest_resistance is not None:
        neutral_summary = (
            f"\u041fока цена находится между поддержкой {nearest_support} "
            f"и сопротивлением {nearest_resistance}, рынок можно считать "
            f"находящимся в локальном диапазоне. \u041fробой одной из границ "
            f"даст более понятный сигнал."
        )
    else:
        neutral_summary = (
            "\u041bокальный диапазон пока определён не полностью, поэтому сценарии "
            "нужно оценивать осторожно."
        )

    return {
        "scenario_up": scenario_up,
        "scenario_down": scenario_down,
        "neutral_summary": neutral_summary,
    }
