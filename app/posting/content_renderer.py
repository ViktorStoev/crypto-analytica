"""Telegram content renderer v2 for crypto-analytica.

This module does not send anything to Telegram. It only converts the existing
analysis JSON from app.analytics.market_analysis.build_analysis() into several
editorial post formats:

- alert
- daily_summary
- deep_dive
- chart_only
- rsi_tutorial
- release_note

The goal is to keep the publishing layer safe: first preview, then wire the
selected renderer into the existing publication flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal

try:
    from app.posting.common import format_interval, get_nested, symbol_hashtags
except ImportError:  # fallback for older branches
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
            "1": "1m", "5": "5m", "15": "15m", "30": "30m",
            "60": "1H", "120": "2H", "240": "4H", "360": "6H",
            "720": "12H", "D": "1D", "1D": "1D",
        }
        return mapping.get(str(interval), str(interval))

    def symbol_hashtags(symbol: str) -> str:
        base = symbol.upper().replace("-", "").replace("/", "")
        tags = [f"#{base}", "#криптоаналитика", "#теханализ"]
        if base.startswith("BTC"):
            tags.insert(1, "#BTC")
        if base.startswith("ETH"):
            tags.insert(1, "#ETH")
        if base.startswith("SOL"):
            tags.insert(1, "#SOL")
        return " ".join(tags)


PostType = Literal[
    "alert",
    "daily_summary",
    "deep_dive",
    "chart_only",
    "rsi_tutorial",
    "release_note",
]

SHORT_DISCLAIMER = (
    "Не финсовет. Это аналитический обзор по данным Bybit; "
    "рынок криптоактивов высокорискован и волатилен."
)

EXTENDED_DISCLAIMER = (
    "Материал носит информационно-аналитический характер и не является "
    "индивидуальной инвестиционной рекомендацией. Данные получены из Bybit "
    "и могут обновляться с задержкой, а сигналы могут давать ложные "
    "срабатывания в условиях высокой волатильности."
)


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
        funding_percent=get_nested(analysis, "funding", "percent"),
        oi_change_24h_percent=get_nested(
            analysis,
            "open_interest",
            "change_24h_percent",
        ),
        trend_direction=str(get_nested(
            analysis,
            "trend",
            "direction",
            default="unknown",
        )),
        trend_comment=str(get_nested(
            analysis,
            "trend",
            "comment",
            default="Недостаточно данных по тренду.",
        )),
        rsi_comment=str(get_nested(
            analysis,
            "rsi",
            "comment",
            default="Недостаточно данных по RSI.",
        )),
        macd_comment=str(get_nested(
            analysis,
            "macd",
            "comment",
            default="Недостаточно данных по MACD.",
        )),
        volume_comment=str(get_nested(
            analysis,
            "volume",
            "comment",
            default="Недостаточно данных по объёму.",
        )),
        funding_comment=str(get_nested(
            analysis,
            "funding",
            "comment",
            default="Недостаточно данных по funding.",
        )),
        oi_comment=str(get_nested(
            analysis,
            "open_interest",
            "comment",
            default="Недостаточно данных по open interest.",
        )),
        summary=str(get_nested(
            analysis,
            "summary",
            "short_comment",
            default="Итог пока не сформирован.",
        )),
        main_risk=str(get_nested(
            analysis,
            "summary",
            "main_risk",
            default="Главный риск пока не определён.",
        )),
        support_levels=list(get_nested(
            analysis,
            "support_resistance",
            "support_levels",
            default=[],
        ) or []),
        resistance_levels=list(get_nested(
            analysis,
            "support_resistance",
            "resistance_levels",
            default=[],
        ) or []),
        scenario_up=str(get_nested(
            analysis,
            "scenarios",
            "scenario_up",
            default="Сценарий роста пока не сформирован.",
        )),
        scenario_down=str(get_nested(
            analysis,
            "scenarios",
            "scenario_down",
            default="Сценарий снижения пока не сформирован.",
        )),
        neutral_summary=str(get_nested(
            analysis,
            "scenarios",
            "neutral_summary",
            default="Нейтральный вывод пока не сформирован.",
        )),
    )


def _money(value: Any) -> str:
    if value is None:
        return "н/д"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(numeric) >= 1000:
        return f"${numeric:,.2f}".replace(",", " ")
    return f"${numeric:.4g}"


def _num(value: Any, suffix: str = "", digits: int = 2, sign: bool = False) -> str:
    if value is None:
        return "н/д"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign_prefix = "+" if sign and numeric > 0 else ""
    return f"{sign_prefix}{numeric:.{digits}f}{suffix}"


def _levels(levels: Iterable[Any], limit: int = 3) -> str:
    selected = list(levels)[:limit]
    if not selected:
        return "н/д"
    return " / ".join(_money(level) for level in selected)


def _clean(text: str) -> str:
    return " ".join(str(text).split())


def _market_mode(facts: MarketFacts) -> str:
    direction = facts.trend_direction
    if direction == "bullish":
        return "структура бычья"
    if direction == "bearish":
        return "структура медвежья"
    if direction == "mixed_bullish":
        return "смешанная картина с бычьим уклоном"
    if direction == "mixed_bearish":
        return "смешанная картина с медвежьим уклоном"
    if direction == "neutral":
        return "рынок без явного направления"
    return "режим рынка не определён"


def _headline(facts: MarketFacts) -> str:
    mode = _market_mode(facts)
    if facts.funding_percent is not None and float(facts.funding_percent) >= 0.05:
        return f"{facts.symbol} на {facts.interval}: {mode}, но funding перегревается"
    if facts.oi_change_24h_percent is not None and abs(float(facts.oi_change_24h_percent)) >= 3:
        return f"{facts.symbol} на {facts.interval}: {mode}, OI заметно меняется"
    return f"{facts.symbol} на {facts.interval}: {mode}"


def build_alert_post(analysis: dict[str, Any]) -> str:
    """Short tactical alert for one symbol."""
    facts = _facts(analysis)
    hashtags = symbol_hashtags(facts.symbol)

    lines = [
        f"⚡️ {_headline(facts)}",
        "",
        _clean(facts.summary),
        "",
        "Метрики:",
        f"• Цена: {_money(facts.price)}",
        f"• EMA 20 / 50 / 200: {_money(facts.ema_20)} / {_money(facts.ema_50)} / {_money(facts.ema_200)}",
        f"• RSI 14: {_num(facts.rsi)}",
        f"• MACD hist: {_num(facts.macd_hist, digits=4, sign=True)}",
        f"• Funding: {_num(facts.funding_percent, suffix='%', digits=4, sign=True)}",
        f"• OI 24h: {_num(facts.oi_change_24h_percent, suffix='%', digits=2, sign=True)}",
        "",
        f"TL;DR: {_clean(facts.neutral_summary)}",
        f"Риск: {_clean(facts.main_risk)}",
        "",
        f"Источник: Bybit · {facts.symbol} · {facts.interval} · {facts.candle_time} UTC",
        SHORT_DISCLAIMER,
        "",
        "Нужен такой же алерт по ETH/SOL?",
        hashtags,
    ]
    return "\n".join(lines).strip()


def build_chart_only_post(analysis: dict[str, Any]) -> str:
    """Very short caption for a future image/chart post."""
    facts = _facts(analysis)
    lines = [
        f"📊 {facts.symbol} · {facts.interval}",
        "",
        f"Цена: {_money(facts.price)}",
        f"RSI: {_num(facts.rsi)} · Funding: {_num(facts.funding_percent, suffix='%', digits=4, sign=True)} · OI 24h: {_num(facts.oi_change_24h_percent, suffix='%', digits=2, sign=True)}",
        "",
        f"TL;DR: {_clean(facts.summary)}",
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
        _headline(facts),
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


def _short_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    for quote in ("USDT", "USDC", "USD"):
        if symbol.endswith(quote):
            return symbol[: -len(quote)]
    return symbol


def build_daily_summary_post(analyses: list[dict[str, Any]]) -> str:
    """Daily market snapshot for several symbols."""
    if not analyses:
        raise ValueError("daily_summary requires at least one analysis item")

    facts_list = [_facts(item) for item in analyses]
    intervals = sorted({facts.interval for facts in facts_list})
    candle_time = facts_list[0].candle_time

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

    lines.extend([
        "",
        "Что важно сейчас:",
    ])

    for facts in facts_list[:3]:
        lines.append(f"• {_short_symbol(facts.symbol)}: {_clean(facts.summary)}")

    lines.extend([
        "",
        "На что смотреть дальше:",
    ])

    for facts in facts_list[:3]:
        if facts.resistance_levels:
            lines.append(
                f"• {_short_symbol(facts.symbol)}: реакция у сопротивления {_levels(facts.resistance_levels, limit=1)}"
            )
        elif facts.support_levels:
            lines.append(
                f"• {_short_symbol(facts.symbol)}: удержание поддержки {_levels(facts.support_levels, limit=1)}"
            )
        else:
            lines.append(f"• {_short_symbol(facts.symbol)}: подтверждение объёмом и динамикой OI")

    lines.extend([
        "",
        f"TL;DR: {_clean(facts_list[0].neutral_summary)}",
        f"Источник: Bybit · таймфреймы {' / '.join(intervals)} · обновление {candle_time} UTC",
        "Не финсовет.",
        "",
        "Какой актив разобрать вечером подробнее: BTC / ETH / SOL?",
        "#crypto_snapshot #криптоаналитика #BTC #ETH #SOL",
    ])

    return "\n".join(lines).strip()


def build_rsi_tutorial_post() -> str:
    return """📘 Как читать RSI в этом канале и не делать ложных выводов

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
#какэтоработает #RSI #криптоаналитика""".strip()


def build_release_note_post() -> str:
    return """🛠 Обновление crypto-analytica

Добавляем новый слой Telegram-контента: теперь один и тот же analysis JSON можно превращать не только в общий обзор, но и в разные форматы постов.

Что появилось:
• alert-пост для коротких рыночных событий
• daily summary для утреннего snapshot
• deep-dive для более подробного разбора
• chart-only caption для будущих графиков
• tutorial и release note как отдельные редакционные форматы

Зачем это нужно:
Проект не должен выглядеть как «чёрный ящик» или канал сигналов. Цель — делать короткие, понятные и проверяемые market snapshots по данным Bybit: что произошло, почему это важно, на каких данных основано и что наблюдать дальше.

Что дальше:
• подключить chart rendering
• добавить confidence score
• добавить event rules для alert-постов
• встроить выбранный формат в текущий Telegram publication flow

GitHub: ViktorStoev/crypto-analytica
#релиз #crypto_analytica #devlog""".strip()


def build_post(
    post_type: PostType,
    analysis: dict[str, Any] | None = None,
    analyses: list[dict[str, Any]] | None = None,
) -> str:
    if post_type == "alert":
        if analysis is None:
            raise ValueError("alert post requires analysis")
        return build_alert_post(analysis)
    if post_type == "chart_only":
        if analysis is None:
            raise ValueError("chart_only post requires analysis")
        return build_chart_only_post(analysis)
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
