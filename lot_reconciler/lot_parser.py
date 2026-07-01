"""Парсинг номера лота вида '56/100 Т', '56/100-1 Т', '29/20-1 Т'.

Формат: <базовый_номер>[-<версия>] <вид_закупки>
    базовый_номер  - "56/100" (число/число)
    версия         - целое число после дефиса; отсутствует => версия 0 (базовая)
    вид_закупки    - одна из букв Т (товары), Р (работы), У (услуги)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_LOT_RE = re.compile(
    r"^\s*(?P<base>\d+\s*/\s*\d+)\s*(?:-\s*(?P<version>\d+))?\s*(?P<kind>[ТРУтру])\s*\.?\s*$"
)

VALID_KINDS = {"Т", "Р", "У"}


@dataclass(frozen=True)
class LotIdentifier:
    """Результат разбора номера лота."""

    raw: str
    base_number: Optional[str] = None
    version: int = 0
    kind: Optional[str] = None
    parse_error: Optional[str] = None
    missing_kind: bool = False

    @property
    def is_parsed(self) -> bool:
        return self.base_number is not None

    @property
    def key(self) -> Optional[tuple]:
        """Ключ сопоставления SAP <-> Портал: базовый номер + вид закупки."""
        if self.base_number is None:
            return None
        return (self.base_number, self.kind)

    @property
    def has_anomaly(self) -> bool:
        return bool(self.parse_error) or self.missing_kind


def _normalize_base(base: str) -> str:
    return re.sub(r"\s*/\s*", "/", base.strip())


def parse_lot_number(raw_value) -> LotIdentifier:
    """Разбирает значение колонки "Идентификатор из внешней системы"."""
    raw_str = "" if raw_value is None else str(raw_value).strip()
    if not raw_str:
        return LotIdentifier(raw=raw_str, parse_error="Пустой номер лота")

    match = _LOT_RE.match(raw_str)
    if not match:
        # Пробуем разобрать без вида закупки (буква Т/Р/У отсутствует).
        loose_match = re.match(
            r"^\s*(?P<base>\d+\s*/\s*\d+)\s*(?:-\s*(?P<version>\d+))?\s*\.?\s*$",
            raw_str,
        )
        if loose_match:
            base = _normalize_base(loose_match.group("base"))
            version = int(loose_match.group("version") or 0)
            return LotIdentifier(
                raw=raw_str,
                base_number=base,
                version=version,
                kind=None,
                missing_kind=True,
            )
        return LotIdentifier(
            raw=raw_str, parse_error=f"Не удалось разобрать номер лота: '{raw_str}'"
        )

    base = _normalize_base(match.group("base"))
    version = int(match.group("version") or 0)
    kind = match.group("kind").upper()
    return LotIdentifier(raw=raw_str, base_number=base, version=version, kind=kind)
