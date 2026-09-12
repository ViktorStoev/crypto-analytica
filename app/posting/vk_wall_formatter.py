from __future__ import annotations

from typing import Any

from app.posting.common import clean_comment
from app.posting.common import format_interval
from app.posting.common import format_levels
from app.posting.common import format_price
from app.posting.common import get_nested
from app.posting.common import symbol_hashtags


def build_vk_wall_post(analysis: dict[str, Any]) -> str:
    symbol = analysis.get("symbol", "UNKNOWN")
    interval = format_interval(analysis.get("interval", "UNKNOWN"))
    candle_time = analysis.get("candle_time", "н/д")

    current_price = get_nested(analysis, "price", "current")
    mark_price = get_nested(analysis, "price", "mark_price")
    index_price = get_nested(analysis, "price", "index_price")

    trend_comment = get_nested(
        analysis,
        "trend",
        "comment",
        default="Нет данных.",
    )
    rsi_comment = get_nested(
        analysis,
        "rsi",
        "comment",
        default="Нет данных.",
    )
    macd_comment = get_nested(
        analysis,
        "macd",
        "comment",
        default="Нет данных.",
    )
    volume_comment = get_nested(
        analysis,
        "volume",
        "comment",
        default="Нет данных.",
    )
    funding_comment = get_nested(
        analysis,
        "funding",
        "comment",
        default="Нет данных.",
    )
    oi_comment = get_nested(
        analysis,
        "open_interest",
        "comment",
        default="Нет данных.",
    )

    support_levels = get_nested(
        analysis,
        "support_resistance",
        "support_levels",
        default=[],
    )
    resistance_levels = get_nested(
        analysis,
        "support_resistance",
        "resistance_levels",
        default=[],
    )

    scenario_up = get_nested(
        analysis,
        "scenarios",
        "scenario_up",
        default="Нет сценария.",
    )
    scenario_down = get_nested(
        analysis,
        "scenarios",
        "scenario_down",
        default="Нет сценария.",
    )
    neutral_summary = get_nested(
        analysis,
        "scenarios",
        "neutral_summary",
        default="Нет вывода.",
    )

    summary_comment = get_nested(
        analysis,
        "summary",
        "short_comment",
        default="Нет итога.",
    )
    main_risk = get_nested(
        analysis,
        "summary",
        "main_risk",
        default="Риски не определены.",
    )

    risk_note = analysis.get(
        "risk_note",
        "Это аналитический обзор по рыночным данным, а не финансовая рекомендация.",
    )

    post = f"""
{symbol} — обзор рынка на {interval}

Свеча/срез данных: {candle_time}

Цена:
• текущая: {format_price(current_price)}
• mark price: {format_price(mark_price)}
• index price: {format_price(index_price)}

Тренд:
{trend_comment}

Импульс:
• RSI: {clean_comment(rsi_comment, ["RSI: ", "RSI "])}
• MACD: {clean_comment(macd_comment, ["MACD: ", "MACD "])}

Объём:
{volume_comment}

Ключевые уровни:
• поддержка: {format_levels(support_levels)}
• сопротивление: {format_levels(resistance_levels)}

Деривативы:
• funding: {clean_comment(funding_comment, ["Funding: ", "Funding "])}
• open interest: {clean_comment(oi_comment, ["Open interest: ", "Open interest "])}

Сценарий роста:
{scenario_up}

Сценарий снижения:
{scenario_down}

Нейтральный вывод:
{neutral_summary}

Итог:
{summary_comment}

Основной риск:
{main_risk}

{risk_note}

{symbol_hashtags(symbol)}
""".strip()

    return post