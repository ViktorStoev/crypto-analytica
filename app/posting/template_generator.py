"""
Telegram post template generator.

Этот модуль получает готовый analysis JSON
и превращает его в человекочитаемый Telegram-пост.
"""

from __future__ import annotations

from typing import Any


def get_nested(data: dict[str, Any], *keys: str, default=None):
    current: Any = data

    for key in keys:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def format_levels(levels: list[float] | None) -> str:
    if not levels:
        return "\u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445"

    return " / ".join(str(level) for level in levels)


def format_price(value) -> str:
    if value is None:
        return "\u043d/\u0434"

    return str(value)


def build_telegram_post(analysis: dict[str, Any]) -> str:
    symbol = analysis.get("symbol", "UNKNOWN")
    interval = analysis.get("interval", "UNKNOWN")

    current_price = get_nested(analysis, "price", "current")
    mark_price = get_nested(analysis, "price", "mark_price")
    index_price = get_nested(analysis, "price", "index_price")

    trend_comment = get_nested(analysis, "trend", "comment", default="\u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445.")
    rsi_comment = get_nested(analysis, "rsi", "comment", default="\u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445.")
    macd_comment = get_nested(analysis, "macd", "comment", default="\u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445.")
    volume_comment = get_nested(analysis, "volume", "comment", default="\u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445.")
    funding_comment = get_nested(analysis, "funding", "comment", default="\u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445.")
    oi_comment = get_nested(analysis, "open_interest", "comment", default="\u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445.")

    support_levels = get_nested(analysis, "support_resistance", "support_levels", default=[])
    resistance_levels = get_nested(analysis, "support_resistance", "resistance_levels", default=[])

    scenario_up = get_nested(analysis, "scenarios", "scenario_up", default="\u041d\u0435\u0442 \u0441\u0446\u0435\u043d\u0430\u0440\u0438\u044f.")
    scenario_down = get_nested(analysis, "scenarios", "scenario_down", default="\u041d\u0435\u0442 \u0441\u0446\u0435\u043d\u0430\u0440\u0438\u044f.")
    neutral_summary = get_nested(analysis, "scenarios", "neutral_summary", default="\u041d\u0435\u0442 \u0432\u044b\u0432\u043e\u0434\u0430.")

    summary_comment = get_nested(analysis, "summary", "short_comment", default="\u041d\u0435\u0442 \u0438\u0442\u043e\u0433\u0430.")
    main_risk = get_nested(analysis, "summary", "main_risk", default="\u0420\u0438\u0441\u043a\u0438 \u043d\u0435 \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0435\u043d\u044b.")
    risk_note = analysis.get(
        "risk_note",
        "\u042d\u0442\u043e \u043d\u0435 \u0444\u0438\u043d\u0430\u043d\u0441\u043e\u0432\u0430\u044f \u0440\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u044f.",
    )

    post = f"""
\U0001f4ca {symbol} / {interval}

\U0001f4b0 \u0426\u0435\u043d\u0430
\u0422\u0435\u043a\u0443\u0449\u0430\u044f: {format_price(current_price)}
Mark price: {format_price(mark_price)}
Index price: {format_price(index_price)}

\U0001f4c8 \u0422\u0440\u0435\u043d\u0434
{trend_comment}

\U0001f4ca \u0418\u043c\u043f\u0443\u043b\u044c\u0441
RSI: {rsi_comment}
MACD: {macd_comment}

\U0001f4e6 \u041e\u0431\u044a\u0451\u043c
{volume_comment}

\U0001f4cd \u0423\u0440\u043e\u0432\u043d\u0438
\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430: {format_levels(support_levels)}
\u0421\u043e\u043f\u0440\u043e\u0442\u0438\u0432\u043b\u0435\u043d\u0438\u0435: {format_levels(resistance_levels)}

\U0001f4b8 \u0414\u0435\u0440\u0438\u0432\u0430\u0442\u0438\u0432\u044b
Funding: {funding_comment}
Open interest: {oi_comment}

\U0001f7e2 \u0421\u0446\u0435\u043d\u0430\u0440\u0438\u0439 \u0440\u043e\u0441\u0442\u0430
{scenario_up}

\U0001f534 \u0421\u0446\u0435\u043d\u0430\u0440\u0438\u0439 \u0441\u043d\u0438\u0436\u0435\u043d\u0438\u044f
{scenario_down}

\U0001f7e1 \u041d\u0435\u0439\u0442\u0440\u0430\u043b\u044c\u043d\u044b\u0439 \u0432\u044b\u0432\u043e\u0434
{neutral_summary}

\U0001f9e0 \u0418\u0442\u043e\u0433
{summary_comment}

\u26a0\ufe0f \u0420\u0438\u0441\u043a
{main_risk}

\u2139\ufe0f {risk_note}
""".strip()

    return post
