"""
Общие вспомогательные функции для analytics-модулей.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

import pandas as pd


def safe_float(value) -> Optional[float]:
    """
    Аккуратно переводит значения из PostgreSQL / pandas в float.
    """

    if value is None:
        return None

    if pd.isna(value):
        return None

    if isinstance(value, Decimal):
        return float(value)

    return float(value)


def round_or_none(value, digits: int = 2):
    value = safe_float(value)

    if value is None:
        return None

    return round(value, digits)
