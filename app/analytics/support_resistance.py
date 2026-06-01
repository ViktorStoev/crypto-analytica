"""
Модуль поиска уровней поддержки/сопротивления.

Идея простая:
1. Берём последние свечи.
2. Ищем локальные минимумы — кандидаты в поддержки.
3. Ищем локальные максимумы — кандидаты в сопротивления.
4. Оставляем ближайшие уровни к текущей цене.
5. Формируем текстовые сценарии.
"""

from __future__ import annotations

from typing import Any

from app.db import get_connection


def to_float(value: Any) -> float | None:
    if value is None:
        return None

    return float(value)


def round_price(value: float | None) -> float | None:
    if value is None:
        return None

    if value >= 1000:
        return round(value, 1)

    if value >= 1:
        return round(value, 4)

    return round(value, 8)


def load_recent_candles(
    symbol: str,
    interval: str,
    limit: int = 240,
) -> list[dict[str, Any]]:
    """
    Загружаем последние свечи из БД.

    Для 1h interval=60 и limit=240 это примерно последние 10 дней.
    """

    query = """
        SELECT
            open_time,
            high_price,
            low_price,
            close_price,
            volume
        FROM candles
        WHERE symbol = %s
          AND interval = %s
        ORDER BY open_time DESC
        LIMIT %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (symbol, interval, limit))
            rows = cur.fetchall()

    candles = []

    for row in rows:
        open_time, high_price, low_price, close_price, volume = row

        candles.append(
            {
                "open_time": open_time,
                "high": to_float(high_price),
                "low": to_float(low_price),
                "close": to_float(close_price),
                "volume": to_float(volume),
            }
        )

    # В БД мы брали DESC, а для анализа удобнее порядок от старых к новым.
    return list(reversed(candles))


def deduplicate_levels(
    levels: list[float],
    current_price: float,
    tolerance_percent: float = 0.002,
) -> list[float]:
    """
    Убираем уровни, которые находятся слишком близко друг к другу.

    tolerance_percent=0.002 означает 0.2%.
    Для BTC около 73600 это примерно 147 долларов.
    """

    if not levels:
        return []

    tolerance = current_price * tolerance_percent
    result: list[float] = []

    for level in sorted(levels):
        if not result:
            result.append(level)
            continue

        if abs(level - result[-1]) >= tolerance:
            result.append(level)

    return result


def find_support_resistance_levels(
    candles: list[dict[str, Any]],
    current_price: float,
    pivot_window: int = 3,
    max_levels: int = 3,
) -> dict[str, Any]:
    """
    Ищем уровни поддержки и сопротивления.

    Поддержка:
    локальный минимум, который находится ниже текущей цены.

    Сопротивление:
    локальный максимум, который находится выше текущей цены.
    """

    if len(candles) < pivot_window * 2 + 1:
        return {
            "support_levels": [],
            "resistance_levels": [],
            "method": "not_enough_candles",
            "candles_used": len(candles),
        }

    support_candidates: list[float] = []
    resistance_candidates: list[float] = []

    for index in range(pivot_window, len(candles) - pivot_window):
        current_candle = candles[index]

        current_low = current_candle["low"]
        current_high = current_candle["high"]

        left = candles[index - pivot_window:index]
        right = candles[index + 1:index + pivot_window + 1]

        neighbor_lows = [c["low"] for c in left + right if c["low"] is not None]
        neighbor_highs = [c["high"] for c in left + right if c["high"] is not None]

        if current_low is not None and neighbor_lows and current_low <= min(neighbor_lows):
            support_candidates.append(current_low)

        if current_high is not None and neighbor_highs and current_high >= max(neighbor_highs):
            resistance_candidates.append(current_high)

    support_candidates = [
        level for level in support_candidates
        if level < current_price
    ]

    resistance_candidates = [
        level for level in resistance_candidates
        if level > current_price
    ]

    support_candidates = deduplicate_levels(
        support_candidates,
        current_price=current_price,
    )

    resistance_candidates = deduplicate_levels(
        resistance_candidates,
        current_price=current_price,
    )

    # Поддержки нужны ближайшие снизу: сортируем от текущей цены вниз.
    support_levels = sorted(
        support_candidates,
        key=lambda level: abs(current_price - level),
    )[:max_levels]

    # Сопротивления нужны ближайшие сверху: сортируем от текущей цены вверх.
    resistance_levels = sorted(
        resistance_candidates,
        key=lambda level: abs(level - current_price),
    )[:max_levels]

    return {
        "support_levels": [round_price(level) for level in support_levels],
        "resistance_levels": [round_price(level) for level in resistance_levels],
        "method": "local_pivots",
        "candles_used": len(candles),
    }


def build_market_scenarios(
    current_price: float,
    support_levels: list[float],
    resistance_levels: list[float],
) -> dict[str, str]:
    nearest_support = support_levels[0] if support_levels else None
    nearest_resistance = resistance_levels[0] if resistance_levels else None

    if nearest_resistance is not None:
        scenario_up = (
            f"Если цена закрепится выше ближайшего сопротивления "
            f"{nearest_resistance}, рынок может попробовать продолжить движение "
            f"к следующей зоне сопротивления. Подтверждением будет рост объёма "
            f"и удержание цены выше пробитого уровня."
        )
    else:
        scenario_up = (
            "Ближайшее сопротивление не определено. Для сценария роста нужно "
            "дождаться формирования новой локальной зоны сверху."
        )

    if nearest_support is not None:
        scenario_down = (
            f"Если цена потеряет ближайшую поддержку {nearest_support}, "
            f"это может усилить давление продавцов. В таком случае рынок может "
            f"пойти к следующей зоне поддержки ниже."
        )
    else:
        scenario_down = (
            "Ближайшая поддержка не определена. Для сценария снижения нужно "
            "дождаться формирования новой локальной зоны снизу."
        )

    if nearest_support is not None and nearest_resistance is not None:
        neutral_summary = (
            f"Пока цена находится между поддержкой {nearest_support} "
            f"и сопротивлением {nearest_resistance}, рынок можно считать "
            f"находящимся в локальном диапазоне. Пробой одной из границ "
            f"даст более понятный сигнал."
        )
    else:
        neutral_summary = (
            "Локальный диапазон пока определён не полностью, поэтому сценарии "
            "нужно оценивать осторожно."
        )

    return {
        "scenario_up": scenario_up,
        "scenario_down": scenario_down,
        "neutral_summary": neutral_summary,
    }


def analyze_support_resistance(
    symbol: str,
    interval: str,
    current_price: float,
    limit: int = 240,
) -> dict[str, Any]:
    candles = load_recent_candles(
        symbol=symbol,
        interval=interval,
        limit=limit,
    )

    levels = find_support_resistance_levels(
        candles=candles,
        current_price=current_price,
    )

    scenarios = build_market_scenarios(
        current_price=current_price,
        support_levels=levels["support_levels"],
        resistance_levels=levels["resistance_levels"],
    )

    return {
        "support_resistance": levels,
        "scenarios": scenarios,
    }
