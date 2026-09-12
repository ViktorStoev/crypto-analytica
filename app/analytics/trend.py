"""
Аналитика тренда.

Здесь живёт логика интерпретации EMA и направления цены.
"""


def interpret_trend(price, ema_20, ema_50, ema_200) -> dict:
    """
    Простая оценка тренда по цене и EMA.

    Это не торговый сигнал.
    Это только текстовое описание структуры рынка.
    """

    if None in [price, ema_20, ema_50, ema_200]:
        return {
            "direction": "unknown",
            "comment": "Недостаточно данных для определения тренда.",
        }

    if price > ema_20 > ema_50 > ema_200:
        return {
            "direction": "bullish",
            "comment": "Цена выше EMA 20/50/200, структура выглядит восходящей.",
        }

    if price < ema_20 < ema_50 < ema_200:
        return {
            "direction": "bearish",
            "comment": "Цена ниже EMA 20/50/200, структура выглядит нисходящей.",
        }

    if price > ema_200:
        return {
            "direction": "mixed_bullish",
            "comment": "Цена выше EMA 200, но средние не выстроены идеально. Картина смешанная с бычьим уклоном.",
        }

    if price < ema_200:
        return {
            "direction": "mixed_bearish",
            "comment": "Цена ниже EMA 200, но средние не выстроены идеально. Картина смешанная с медвежьим уклоном.",
        }

    return {
        "direction": "neutral",
        "comment": "Цена находится около ключевых средних, выраженного направления нет.",
    }
