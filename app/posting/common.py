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
        return "нет данных"

    return " / ".join(str(level) for level in levels)


def format_price(value) -> str:
    if value is None:
        return "н/д"

    return str(value)


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


def clean_comment(comment: str, prefixes: list[str]) -> str:
    for prefix in prefixes:
        if comment.startswith(prefix):
            return comment[len(prefix):].strip()

    return comment


def symbol_hashtags(symbol: str) -> str:
    base = symbol.upper().replace("-", "").replace("/", "")

    tags = [
        f"#{base}",
        "#криптовалюта",
        "#криптоаналитика",
        "#теханализ",
    ]

    if base.startswith("BTC"):
        tags.insert(1, "#BTC")

    if base.startswith("ETH"):
        tags.insert(1, "#ETH")

    if base.startswith("SOL"):
        tags.insert(1, "#SOL")

    return " ".join(tags)