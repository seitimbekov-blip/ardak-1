"""Разбор числовых значений из ячеек Excel (учитывает разделители тысяч/десятичных)."""
from __future__ import annotations

from typing import Optional


def to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\xa0", "").replace(" ", "")
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def values_equal(a, b, *, numeric_tolerance: float = 0.01) -> bool:
    """Сравнивает два значения ячеек: числа - с допуском, текст - без учета
    регистра и лишних пробелов, None/пустая строка считаются эквивалентными."""
    a_num, b_num = to_float(a), to_float(b)
    if a_num is not None and b_num is not None:
        return abs(a_num - b_num) < numeric_tolerance

    def norm_text(v) -> str:
        if v is None:
            return ""
        return " ".join(str(v).strip().lower().split())

    return norm_text(a) == norm_text(b)
