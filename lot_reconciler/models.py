"""Общие структуры данных для сверки лотов SAP <-> Портал закупок."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from lot_reconciler.lot_parser import LotIdentifier

# Поля сравнения, которые проверяются в первую очередь (раздел 5 PRD, F7).
PRIMARY_COMPARE_FIELDS: List[str] = [
    "month",
    "quantity",
    "unit_price",
    "priority",
    "method",
    "address",
]

# Остальные поля, участвующие в полном сравнении.
SECONDARY_COMPARE_FIELDS: List[str] = [
    "sum_no_vat",
    "sum_with_vat",
    "delivery_terms",
    "payment_terms",
]

ALL_COMPARE_FIELDS: List[str] = PRIMARY_COMPARE_FIELDS + SECONDARY_COMPARE_FIELDS

FIELD_LABELS: Dict[str, str] = {
    "month": "Срок осуществления закупки (месяц)",
    "quantity": "Кол-во, объём",
    "unit_price": "Маркетинговая цена за единицу",
    "priority": "Приоритет закупки",
    "method": "Способ закупок",
    "address": "Адрес поставки/выполнения/оказания",
    "sum_no_vat": "Сумма без НДС",
    "sum_with_vat": "Сумма с НДС",
    "delivery_terms": "Условия поставки",
    "payment_terms": "Условия оплаты",
}


class Source(str, Enum):
    SAP = "SAP"
    PORTAL = "PORTAL"


class LotStatus(str, Enum):
    ADD = "ДОБАВИТЬ"
    CHANGE = "ИЗМЕНИТЬ"
    REMOVE = "ИСКЛЮЧИТЬ"
    UNCHANGED = "БЕЗ ИЗМЕНЕНИЙ"


# Значения "Тип действия" ожидаемые em_agent.py.
EM_AGENT_ACTION_VALUES: Dict[LotStatus, str] = {
    LotStatus.ADD: "добавить",
    LotStatus.CHANGE: "изменить",
    LotStatus.REMOVE: "исключить",
}


@dataclass
class LotRecord:
    """Одна строка лота из файла SAP или Портала после разбора."""

    source: Source
    row_number: int
    identifier: LotIdentifier
    fields: Dict[str, Any] = field(default_factory=dict)
    raw_row: Dict[str, Any] = field(default_factory=dict)
    action_type_reference: Optional[str] = None  # только для SAP, колонка B (F6a)


@dataclass
class Anomaly:
    """Аномалия, требующая ручной проверки (F4). Не блокирует экспорт."""

    kind: str
    message: str
    lot_key: Optional[tuple] = None
    row_numbers: List[int] = field(default_factory=list)


@dataclass
class FieldDiff:
    field: str
    label: str
    sap_value: Any
    portal_value: Any


@dataclass
class ComparisonResult:
    lot_key: tuple
    status: LotStatus
    sap_record: Optional[LotRecord]
    portal_record: Optional[LotRecord]
    diffs: List[FieldDiff] = field(default_factory=list)

    @property
    def base_number(self) -> str:
        return self.lot_key[0]

    @property
    def kind(self) -> Optional[str]:
        return self.lot_key[1]

    @property
    def display_lot_number(self) -> str:
        record = self.sap_record or self.portal_record
        if record is not None:
            return record.identifier.raw
        kind = self.kind or ""
        return f"{self.base_number} {kind}".strip()

    @property
    def action_type_reference(self) -> Optional[str]:
        return self.sap_record.action_type_reference if self.sap_record else None


@dataclass
class ReconciliationReport:
    results: List[ComparisonResult]
    anomalies: List[Anomaly]
    sap_row_count: int
    portal_row_count: int

    def counts_by_status(self) -> Dict[str, int]:
        counts = {status.value: 0 for status in LotStatus}
        for result in self.results:
            counts[result.status.value] += 1
        return counts
