"""Telegram content renderer v3 for crypto-analytica.

This module does not send anything to Telegram.
It converts the existing analysis JSON from
app.analytics.market_analysis.build_analysis() into editorial post formats.

Main idea:
- market_snapshot: regular market state, safe to publish every few hours
- deep_dive: main analytical format
- alert: event-driven only; no event = no alert post
- daily_summary: BTC + ETH + SOL style summary
- chart_caption / chart_only: short caption for an attached chart
- rsi_tutorial: static education post
- release_note: static devlog post
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal

try:
    from app.posting.common import format_interval, get_nested, symbol_hashtags
except ImportError:
    # Fallback for older branches where app.posting.common does not exist yet.
    def get_nested(data: dict[str, Any], *keys: str, default=None):
        current: Any = data
        for key in keys:
            if not isinstance(current, dict):
                return default
            current = current.get(key)
            if current is None:
                return default
        return current

    def format_interval(interval: str) -> str:
        mapping = {
            "1": "1m",
            "5": "5m",
            "15": "15m",
            "30": "30m",
            "60": "1H",
            "120": "2H",
            "240": "4H",
            "360": "6H",
            "720": "12H",
            "D": "1D",
            "1D": "1D",
        }
        return mapping.get(str(interval), str(interval))

    def symbol_hashtags(symbol: str) -> str:
        base = symbol.upper().replace("-", "").replace("/", "")
        tags = [f"#{base}", "#криптовалюта", "#криптоаналитика", "#теханализ"]
        if base.startswith("BTC"):
            tags.insert(1, "#BTC")
        if base.startswith("ETH"):
            tags.insert(1, "#ETH")
        if base.startswith("SOL"):
            tags.insert(1, "#SOL")
        return " ".join(tags)


PostType = Literal[
    "market_snapshot",
    "alert",
    "daily_summary",
    "deep_dive",
    "chart_caption",
    "chart_only",
    "rsi_tutorial",
    "release_note",
]


SHORT_DISCLAIMER = (
    "Не финсовет. Это аналитический обзор; "
    "рынок криптоактивов высокорискован и волатилен."
)

EXTENDED_DISCLAIMER = (
    "Материал носит информационно-аналитический характер и не является "
    "индивидуальной инвестиционной рекомендацией. Данные полученые из источников "
    "могут обновляться с задержкой, а сигналы могут давать ложные "
    "срабатывания в условиях высокой волатильности."
)


class NoAlertEventError(ValueError):
    """Raised when --type alert was requested, but no event rule fired."""


@dataclass(frozen=True)
class MarketFacts:
    symbol: str
    interval: str
    candle_time: str
    price: Any
    mark_price: Any
    index_price: Any
    ema_20: Any
    ema_50: Any
    ema_200: Any
    rsi: Any
    macd_hist: Any
    volume_ratio: Any
    funding_percent: Any
    oi_change_24h_percent: Any
    trend_direction: str
    trend_comment: str
    rsi_comment: str
    macd_comment: str
    volume_comment: str
    funding_comment: str
    oi_comment: str
    summary: str
    main_risk: str
    support_levels: list[Any]
    resistance_levels: list[Any]
    scenario_up: str
    scenario_down: str
    neutral_summary: str


@dataclass(frozen=True)
class AlertEvent:
    kind: str
    emoji: str
    title: str
    what_happened: str
    why_it_matters: str
    next_zone: str
    risk: str
    severity: str


def _facts(analysis: dict[str, Any]) -> MarketFacts:
    symbol = str(analysis.get("symbol", "UNKNOWN")).upper()
    interval = format_interval(str(analysis.get("interval", "UNKNOWN")))

    return MarketFacts(
        symbol=symbol,
        interval=interval,
        candle_time=str(analysis.get("candle_time", "н/д")),
        price=get_nested(analysis, "price", "current"),
        mark_price=get_nested(analysis, "price", "mark_price"),
        index_price=get_nested(analysis, "price", "index_price"),
        ema_20=get_nested(analysis, "ema", "ema_20"),
        ema_50=get_nested(analysis, "ema", "ema_50"),
        ema_200=get_nested(analysis, "ema", "ema_200"),
        rsi=get_nested(analysis, "rsi", "value"),
        macd_hist=get_nested(analysis, "macd", "hist"),
        volume_ratio=get_nested(analysis, "volume", "ratio"),
        funding_percent=get_nested(analysis, "funding", "percent"),
        oi_change_24h_percent=get_nested(
            analysis,
            "open_interest",
            "change_24h_percent",
        ),
        trend_direction=str(
            get_nested(analysis, "trend", "direction", default="unknown")
        ),
        trend_comment=str(
            get_nested(
                analysis,
                "trend",
                "comment",
                default="Недостаточно данных по тренду.",
            )
        ),
        rsi_comment=str(
            get_nested(
                analysis,
                "rsi",
                "comment",
                default="Недостаточно данных по RSI.",
            )
        ),
        macd_comment=str(
            get_nested(
                analysis,
                "macd",
                "comment",
                default="Недостаточно данных по MACD.",
            )
        ),
        volume_comment=str(
            get_nested(
                analysis,
                "volume",
                "comment",
                default="Недостаточно данных по объёму.",
            )
        ),
        funding_comment=str(
            get_nested(
                analysis,
                "funding",
                "comment",
                default="Недостаточно данных по funding.",
            )
        ),
        oi_comment=str(
            get_nested(
                analysis,
                "open_interest",
                "comment",
                default="Недостаточно данных по open interest.",
            )
        ),
        summary=str(
            get_nested(
                analysis,
                "summary",
                "short_comment",
                default="Итог пока не сформирован.",
            )
        ),
        main_risk=str(
            get_nested(
                analysis,
                "summary",
                "main_risk",
                default="Главный риск пока не определён.",
            )
        ),
        support_levels=list(
            get_nested(
                analysis,
                "support_resistance",
                "support_levels",
                default=[],
            )
            or []
        ),
        resistance_levels=list(
            get_nested(
                analysis,
                "support_resistance",
                "resistance_levels",
                default=[],
            )
            or []
        ),
        scenario_up=str(
            get_nested(
                analysis,
                "scenarios",
                "scenario_up",
                default="Сценарий роста пока не сформирован.",
            )
        ),
        scenario_down=str(
            get_nested(
                analysis,
                "scenarios",
                "scenario_down",
                default="Сценарий снижения пока не сформирован.",
            )
        ),
        neutral_summary=str(
            get_nested(
                analysis,
                "scenarios",
                "neutral_summary",
                default="Нейтральный вывод пока не сформирован.",
            )
        ),
    )


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(value: Any) -> str:
    numeric = _as_float(value)
    if numeric is None:
        return "н/д"
    if abs(numeric) >= 1000:
        return f"${numeric:,.2f}".replace(",", " ")
    return f"${numeric:.4g}"


def _num(value: Any, suffix: str = "", digits: int = 2, sign: bool = False) -> str:
    numeric = _as_float(value)
    if numeric is None:
        return "н/д"
    sign_prefix = "+" if sign and numeric > 0 else ""
    return f"{sign_prefix}{numeric:.{digits}f}{suffix}"


def _levels(levels: Iterable[Any], limit: int = 3) -> str:
    selected = list(levels)[:limit]
    if not selected:
        return "н/д"
    return " / ".join(_money(level) for level in selected)


def _clean(text: str) -> str:
    return " ".join(str(text).split())


def _short_sentence(text: str, max_chars: int = 170) -> str:
    cleaned = _clean(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _market_mode(facts: MarketFacts) -> str:
    direction = facts.trend_direction

    if direction in {"strong_bullish", "bullish"}:
        return "структура бычья"
    if direction in {"strong_bearish", "bearish"}:
        return "структура медвежья"
    if direction == "mixed_bullish":
        return "смешанная картина с бычьим уклоном"
    if direction == "mixed_bearish":
        return "смешанная картина с медвежьим уклоном"
    if direction == "neutral":
        return "рынок без явного направления"

    return "режим рынка не определён"


def _short_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    for quote in ("USDT", "USDC", "USD"):
        if symbol.endswith(quote):
            return symbol[: -len(quote)]
    return symbol


def _first_support(facts: MarketFacts) -> Any:
    return facts.support_levels[0] if facts.support_levels else None


def _first_resistance(facts: MarketFacts) -> Any:
    return facts.resistance_levels[0] if facts.resistance_levels else None


def _next_zone_after_resistance(facts: MarketFacts) -> str:
    if len(facts.resistance_levels) >= 2:
        return _levels(facts.resistance_levels[:2], limit=2)
    if facts.resistance_levels:
        return _levels(facts.resistance_levels, limit=1)
    return "следующая зона сопротивления не определена"


def _next_zone_after_support(facts: MarketFacts) -> str:
    if len(facts.support_levels) >= 2:
        return _levels(facts.support_levels[:2], limit=2)
    if facts.support_levels:
        return _levels(facts.support_levels, limit=1)
    return "следующая зона поддержки не определена"


def _detect_alert_event(facts: MarketFacts) -> AlertEvent | None:
    """Detect event-driven alert from the current analysis snapshot.

    Important limitation:
    With only one analysis JSON we cannot reliably prove that a level has just
    been broken. The level rules below work only when the current support /
    resistance output still contains a crossed level. A stricter breakout rule
    should later compare current analysis with the previous saved analysis.
    """

    price = _as_float(facts.price)
    support = _as_float(_first_support(facts))
    resistance = _as_float(_first_resistance(facts))
    volume_ratio = _as_float(facts.volume_ratio)
    funding = _as_float(facts.funding_percent)
    oi_change = _as_float(facts.oi_change_24h_percent)
    rsi = _as_float(facts.rsi)

    if price is not None and resistance is not None and price > resistance:
        return AlertEvent(
            kind="resistance_breakout",
            emoji="⚡️",
            title=f"{facts.symbol} пробил сопротивление {_money(resistance)}",
            what_happened=(
                f"Цена {facts.symbol} закрепилась выше ближайшего "
                f"сопротивления {_money(resistance)} на {facts.interval}."
            ),
            why_it_matters=(
                "Пробой уровня может открыть движение к следующей зоне, "
                "если его подтвердят объём, импульс и удержание цены выше уровня."
            ),
            next_zone=_next_zone_after_resistance(facts),
            risk="Ложный пробой и возврат под пробитое сопротивление.",
            severity="high",
        )

    if price is not None and support is not None and price < support:
        return AlertEvent(
            kind="support_breakdown",
            emoji="⚠️",
            title=f"{facts.symbol} потерял поддержку {_money(support)}",
            what_happened=(
                f"Цена {facts.symbol} ушла ниже ближайшей поддержки "
                f"{_money(support)} на {facts.interval}."
            ),
            why_it_matters=(
                "Потеря поддержки может усилить давление продавцов, "
                "особенно если движение подтверждается объёмом и ухудшением импульса."
            ),
            next_zone=_next_zone_after_support(facts),
            risk="Ложный прокол поддержки и быстрый возврат в диапазон.",
            severity="high",
        )

    if volume_ratio is not None and volume_ratio >= 1.8:
        return AlertEvent(
            kind="volume_spike",
            emoji="🔥",
            title=f"{facts.symbol}: резкий всплеск объёма на {facts.interval}",
            what_happened=(
                f"Текущий объём примерно в {_num(volume_ratio, digits=2)}x "
                "выше среднего за 20 свечей."
            ),
            why_it_matters=(
                "Рост объёма часто показывает, что движение стало важнее обычного шума. "
                "Теперь нужно смотреть, удержит ли цена ближайший ключевой уровень."
            ),
            next_zone=(
                f"сопротивление {_levels(facts.resistance_levels, limit=1)} / "
                f"поддержка {_levels(facts.support_levels, limit=1)}"
            ),
            risk="Объём может быть связан с выносом ликвидности, а не с устойчивым трендом.",
            severity="medium",
        )

    if oi_change is not None and abs(oi_change) >= 3:
        direction = "растёт" if oi_change > 0 else "снижается"
        meaning = (
            "в рынок заходят новые позиции"
            if oi_change > 0
            else "часть позиций закрывается"
        )
        return AlertEvent(
            kind="open_interest_anomaly",
            emoji="📈" if oi_change > 0 else "📉",
            title=(
                f"{facts.symbol}: Open Interest {direction} "
                f"на {_num(oi_change, suffix='%', digits=2, sign=True)}"
            ),
            what_happened=(
                f"Open interest за 24h {direction}: "
                f"{_num(oi_change, suffix='%', digits=2, sign=True)}."
            ),
            why_it_matters=(
                f"Это может означать, что {meaning}. Важно сопоставить OI "
                "с направлением цены, funding и объёмом."
            ),
            next_zone=(
                f"сопротивление {_levels(facts.resistance_levels, limit=1)} / "
                f"поддержка {_levels(facts.support_levels, limit=1)}"
            ),
            risk="OI сам по себе не даёт направления: возможны и продолжение, и резкий squeeze.",
            severity="medium",
        )

    if funding is not None and abs(funding) >= 0.05:
        side = "лонгов" if funding > 0 else "шортов"
        return AlertEvent(
            kind="funding_extreme",
            emoji="💸",
            title=f"{facts.symbol}: funding показывает перегрев {side}",
            what_happened=(
                f"Funding достиг {_num(funding, suffix='%', digits=4, sign=True)}."
            ),
            why_it_matters=(
                "Сильный funding-перекос повышает риск резкого движения против "
                "переполненной стороны рынка."
            ),
            next_zone=(
                f"сопротивление {_levels(facts.resistance_levels, limit=1)} / "
                f"поддержка {_levels(facts.support_levels, limit=1)}"
            ),
            risk="Funding может долго оставаться экстремальным в сильном тренде.",
            severity="medium",
        )

    if rsi is not None and (rsi >= 70 or rsi <= 30):
        state = "перегрет вверх" if rsi >= 70 else "перепродан"
        return AlertEvent(
            kind="rsi_extreme",
            emoji="🌡",
            title=f"{facts.symbol}: RSI {state} на {facts.interval}",
            what_happened=f"RSI 14 сейчас {_num(rsi)}.",
            why_it_matters=(
                "Экстремальный RSI показывает сильный импульс, но не является "
                "самостоятельным сигналом BUY/SELL."
            ),
            next_zone=(
                f"сопротивление {_levels(facts.resistance_levels, limit=1)} / "
                f"поддержка {_levels(facts.support_levels, limit=1)}"
            ),
            risk="В трендовом рынке RSI может оставаться экстремальным дольше ожидаемого.",
            severity="low",
        )

    return None


def build_market_snapshot_post(analysis: dict[str, Any]) -> str:
    """Regular short market state post. This is not an alert."""

    facts = _facts(analysis)
    hashtags = symbol_hashtags(facts.symbol)

    lines = [
        f"🧭 Market snapshot: {facts.symbol} · {facts.interval}",
        "",
        f"Режим: {_market_mode(facts)}",
        f"Цена: {_money(facts.price)}",
        "",
        "Ключевые метрики:",
        f"• EMA 20 / 50 / 200: {_money(facts.ema_20)} / {_money(facts.ema_50)} / {_money(facts.ema_200)}",
        f"• RSI 14: {_num(facts.rsi)}",
        f"• MACD hist: {_num(facts.macd_hist, digits=4, sign=True)}",
        f"• Volume/SMA20: {_num(facts.volume_ratio, digits=2)}x",
        f"• Funding: {_num(facts.funding_percent, suffix='%', digits=4, sign=True)}",
        f"• OI 24h: {_num(facts.oi_change_24h_percent, suffix='%', digits=2, sign=True)}",
        "",
        f"Что важно: {_short_sentence(facts.summary, 210)}",
        f"На что смотреть: поддержка {_levels(facts.support_levels, limit=1)} / сопротивление {_levels(facts.resistance_levels, limit=1)}",
        "",
        f"TL;DR: {_short_sentence(facts.neutral_summary, 180)}",
        f"Источник: Bybit · {facts.symbol} · {facts.interval} · {facts.candle_time} UTC",
        SHORT_DISCLAIMER,
        hashtags,
    ]

    return "\n".join(lines).strip()


def build_alert_post(analysis: dict[str, Any]) -> str:
    """Event-driven alert for one symbol.

    If no rule fired, this function raises NoAlertEventError.
    Use market_snapshot for regular non-event posts.
    """

    facts = _facts(analysis)
    event = _detect_alert_event(facts)

    if event is None:
        raise NoAlertEventError(
            f"No alert event detected for {facts.symbol} {facts.interval}. "
            "Use --type market_snapshot for a regular market state post."
        )

    lines = [
        f"{event.emoji} {event.title}",
        "",
        "Что произошло:",
        event.what_happened,
        "",
        "Почему важно:",
        event.why_it_matters,
        "",
        "Метрики:",
        f"• Цена: {_money(facts.price)}",
        f"• RSI 14: {_num(facts.rsi)}",
        f"• Volume/SMA20: {_num(facts.volume_ratio, digits=2)}x",
        f"• Funding: {_num(facts.funding_percent, suffix='%', digits=4, sign=True)}",
        f"• OI 24h: {_num(facts.oi_change_24h_percent, suffix='%', digits=2, sign=True)}",
        "",
        f"Следующая зона: {event.next_zone}",
        f"Риск: {event.risk}",
        "",
        f"Источник: Bybit · {facts.symbol} · {facts.interval} · {facts.candle_time} UTC",
        SHORT_DISCLAIMER,
        symbol_hashtags(facts.symbol),
    ]

    return "\n".join(lines).strip()


def build_chart_caption_post(analysis: dict[str, Any]) -> str:
    """Short caption for a chart/image post.

    This format should be used together with an attached chart.
    """

    facts = _facts(analysis)

    lines = [
        f"📊 {facts.symbol} · {facts.interval}",
        "",
        f"Цена: {_money(facts.price)}",
        (
            f"RSI: {_num(facts.rsi)} · "
            f"Funding: {_num(facts.funding_percent, suffix='%', digits=4, sign=True)} · "
            f"OI 24h: {_num(facts.oi_change_24h_percent, suffix='%', digits=2, sign=True)}"
        ),
        "",
        f"TL;DR: {_short_sentence(facts.summary, 150)}",
        f"Источник: Bybit · {facts.candle_time} UTC",
        "Не финсовет.",
        symbol_hashtags(facts.symbol),
    ]

    return "\n".join(lines).strip()


def build_deep_dive_post(analysis: dict[str, Any]) -> str:
    """Longer analytical post for experienced readers."""

    facts = _facts(analysis)

    lines = [
        f"🧠 Разбор {facts.symbol} · {facts.interval}",
        "",
        f"{facts.symbol} на {facts.interval}: {_market_mode(facts)}",
        "",
        "1. Структура цены",
        _clean(facts.trend_comment),
        f"EMA 20 / 50 / 200: {_money(facts.ema_20)} / {_money(facts.ema_50)} / {_money(facts.ema_200)}",
        f"Ближайшая поддержка: {_levels(facts.support_levels)}",
        f"Ближайшее сопротивление: {_levels(facts.resistance_levels)}",
        "",
        "2. Импульс",
        f"RSI 14: {_num(facts.rsi)} — {_clean(facts.rsi_comment)}",
        f"MACD hist: {_num(facts.macd_hist, digits=4, sign=True)} — {_clean(facts.macd_comment)}",
        "",
        "3. Объём и деривативы",
        _clean(facts.volume_comment),
        f"Funding: {_num(facts.funding_percent, suffix='%', digits=4, sign=True)} — {_clean(facts.funding_comment)}",
        f"Open interest 24h: {_num(facts.oi_change_24h_percent, suffix='%', digits=2, sign=True)} — {_clean(facts.oi_comment)}",
        "",
        "4. Сценарии",
        f"🟢 Рост: {_clean(facts.scenario_up)}",
        f"🔴 Снижение: {_clean(facts.scenario_down)}",
        f"🟡 База: {_clean(facts.neutral_summary)}",
        "",
        f"Вывод: {_clean(facts.summary)}",
        f"Главный риск: {_clean(facts.main_risk)}",
        "",
        f"Источник: Bybit · {facts.symbol} · {facts.interval} · OI по нормализованному интервалу · {facts.candle_time} UTC",
        EXTENDED_DISCLAIMER,
        "",
        "Продолжать такие deep-dive по ETH/SOL?",
        symbol_hashtags(facts.symbol),
    ]

    return "\n".join(lines).strip()


def build_daily_summary_post(analyses: list[dict[str, Any]]) -> str:
    """Daily market snapshot for BTC + ETH + SOL style summaries."""

    if len(analyses) < 3:
        raise ValueError(
            "daily_summary requires at least 3 symbols, for example: "
            "--symbols BTCUSDT ETHUSDT SOLUSDT. "
            "For one symbol use --type market_snapshot."
        )

    facts_list = [_facts(item) for item in analyses]
    intervals = sorted({facts.interval for facts in facts_list})
    candle_time = facts_list[0].candle_time

    leaders = sorted(
        facts_list,
        key=lambda item: abs((_as_float(item.rsi) or 50.0) - 50.0),
        reverse=True,
    )

    lines = [
        "🌅 Утренний crypto snapshot",
        "",
        "Рынок сейчас выглядит так:",
        "",
    ]

    for facts in facts_list:
        lines.append(
            f"• {_short_symbol(facts.symbol)} — {_money(facts.price)}, "
            f"{_market_mode(facts)}, RSI {_num(facts.rsi)}"
        )

    lines.extend(["", "Что важно сейчас:"])

    for facts in facts_list[:3]:
        lines.append(
            f"• {_short_symbol(facts.symbol)}: {_short_sentence(facts.summary, 130)}"
        )

    lines.extend(["", "На что смотреть дальше:"])

    for facts in facts_list[:3]:
        if facts.resistance_levels:
            lines.append(
                f"• {_short_symbol(facts.symbol)}: реакция у сопротивления "
                f"{_levels(facts.resistance_levels, limit=1)}"
            )
        elif facts.support_levels:
            lines.append(
                f"• {_short_symbol(facts.symbol)}: удержание поддержки "
                f"{_levels(facts.support_levels, limit=1)}"
            )
        else:
            lines.append(
                f"• {_short_symbol(facts.symbol)}: подтверждение объёмом и динамикой OI"
            )

    strongest = leaders[0]
    lines.extend(
        [
            "",
            (
                "TL;DR: рынок неоднородный; самый заметный импульс сейчас у "
                f"{_short_symbol(strongest.symbol)}, но решение нужно сверять "
                "с уровнями, объёмом и derivatives."
            ),
            f"Источник: Bybit · таймфреймы {' / '.join(intervals)} · обновление {candle_time} UTC",
            "Не финсовет.",
            "",
            "Какой актив разобрать вечером подробнее: BTC / ETH / SOL?",
            "#crypto_snapshot #криптоаналитика #BTC #ETH #SOL",
        ]
    )

    return "\n".join(lines).strip()


def build_rsi_tutorial_post() -> str:
    return """
📘 Как читать RSI в этом канале и не делать ложных выводов

RSI — это не кнопка BUY/SELL. В crypto-analytica RSI используется как индикатор состояния импульса, а не как самостоятельный торговый сигнал.

Как мы читаем RSI:
• выше 70 — рынок может быть перегрет вверх
• ниже 30 — рынок может быть перепродан
• выше 55 — импульс умеренно сильный
• ниже 45 — импульс ослаблен
• 45–55 — нейтральная зона

Что важно понимать:
RSI 72 не означает «срочно шортить». Если цена выше EMA 20/50/200, MACD положительный и объём подтверждает движение, перегретость может держаться дольше, чем кажется.

Правильный вопрос не «RSI высокий, значит падение?», а «RSI высокий — и что при этом делают тренд, объём, funding и OI?»

TL;DR: RSI показывает состояние импульса, но решение нельзя строить по одному индикатору.

Не финсовет. Это образовательный пост о том, как читать аналитику канала.

Следующим постом разобрать funding rate таким же простым языком?
#какэтоработает #RSI #криптоаналитика
""".strip()


def build_release_note_post() -> str:
    return """
🛠 Обновление crypto-analytica

Переделали редакционную систему постов.

Главное изменение:
• старый alert переезжает в market_snapshot
• настоящий alert теперь строится только при событии
• deep_dive остаётся основным аналитическим разбором
• chart_caption используется как подпись к графику, а не как самостоятельный пост
• daily_summary рассчитан на BTC + ETH + SOL

Почему это важно:
Канал не должен кричать «alert», когда рынок просто стоит в диапазоне. Обычные рыночные срезы должны выходить как snapshot, а alert — только при пробое уровня, всплеске объёма, аномалии OI, экстремальном funding или RSI.

Что дальше:
• добавить хранение предыдущего analysis snapshot
• сделать более строгие breakout rules
• подключить chart rendering
• добавить confidence score

GitHub: ViktorStoev/crypto-analytica
#релиз #crypto_analytica #devlog
""".strip()


def build_post(
    post_type: PostType,
    analysis: dict[str, Any] | None = None,
    analyses: list[dict[str, Any]] | None = None,
) -> str:
    if post_type == "market_snapshot":
        if analysis is None:
            raise ValueError("market_snapshot post requires analysis")
        return build_market_snapshot_post(analysis)

    if post_type == "alert":
        if analysis is None:
            raise ValueError("alert post requires analysis")
        return build_alert_post(analysis)

    if post_type in {"chart_caption", "chart_only"}:
        if analysis is None:
            raise ValueError("chart_caption post requires analysis")
        return build_chart_caption_post(analysis)

    if post_type == "deep_dive":
        if analysis is None:
            raise ValueError("deep_dive post requires analysis")
        return build_deep_dive_post(analysis)

    if post_type == "daily_summary":
        if analyses is None:
            raise ValueError("daily_summary post requires analyses")
        return build_daily_summary_post(analyses)

    if post_type == "rsi_tutorial":
        return build_rsi_tutorial_post()

    if post_type == "release_note":
        return build_release_note_post()

    raise ValueError(f"Unsupported post type: {post_type}")
