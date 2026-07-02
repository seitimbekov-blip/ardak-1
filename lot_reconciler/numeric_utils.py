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


_EMPTY_PLACEHOLDERS = {"-", "--", "н/д", "нет"}


def norm_text(v) -> str:
    """Нормализует текстовое значение: None и распространенные плейсхолдеры
    пустого значения ('-', 'н/д' и т.п., используются и в SAP, и на Портале)
    приводятся к пустой строке, чтобы не считаться расхождением."""
    if v is None:
        return ""
    text = " ".join(str(v).strip().lower().split())
    if text in _EMPTY_PLACEHOLDERS:
        return ""
    return text


def values_equal(a, b, *, numeric_tolerance: float = 0.01) -> bool:
    """Сравнивает два значения ячеек: числа - с допуском, текст - без учета
    регистра, лишних пробелов и плейсхолдеров пустого значения."""
    a_num, b_num = to_float(a), to_float(b)
    if a_num is not None and b_num is not None:
        return abs(a_num - b_num) < numeric_tolerance

    return norm_text(a) == norm_text(b)
