"""Загрузка выгрузки плана закупок с Портала закупок Фонда (или ИСЭЗ 2.0 -
для целей сравнения формат равнозначен).

Структура (см. PRD, раздел 5):
- Заголовки на строке 9, данные - со строки 12.
- Между категориями встречаются строки-разделители ("1. Товары", "2. Работы",
  "3. Услуги") - пропускаются при парсинге.
- Колонка B - номер лота ("Идентификатор из внешней системы (служебное поле)").
- Колонка S - сумма без НДС.
- Файл содержит только лоты, уже загруженные на портал (актуальный план).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Union

from openpyxl import load_workbook

from lot_reconciler.excel_utils import (
    load_field_config,
    resolve_columns,
    worksheet_max_col_with_data,
)
from lot_reconciler.lot_parser import parse_lot_number
from lot_reconciler.models import Anomaly, LotRecord, Source
from lot_reconciler.numeric_utils import to_float

HEADER_ROWS = [9]
# Сразу после заголовка нередко идет служебная строка с номерами колонок
# (1,2,3,...) - она отбрасывается как аномалия "нет номера лота", поэтому
# стартуем сразу после заголовка, а не с жестко заданного отступа.
DATA_START_ROW = 10

_CATEGORY_SEPARATOR_RE = re.compile(
    r"^\s*\d+\.\s*(товары|работы|услуги)\s*$", re.IGNORECASE
)


def _is_category_separator(row_values: Dict[int, object]) -> bool:
    for value in row_values.values():
        if value is None:
            continue
        text = str(value).strip()
        if text and _CATEGORY_SEPARATOR_RE.match(text):
            return True
    return False


@dataclass
class PortalLoadResult:
    records: List[LotRecord] = field(default_factory=list)
    anomalies: List[Anomaly] = field(default_factory=list)
    unresolved_fields: List[str] = field(default_factory=list)
    column_map: Dict[str, int] = field(default_factory=dict)
    max_col: int = 0
    total_rows_read: int = 0


def load_portal_file(
    path_or_buffer: Union[str, Path, object],
    field_config: dict = None,
) -> PortalLoadResult:
    config = field_config or load_field_config()["portal"]
    wb = load_workbook(path_or_buffer, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    max_col = worksheet_max_col_with_data(ws)

    mapping, unresolved = resolve_columns(ws, HEADER_ROWS, max_col, config)
    result = PortalLoadResult(unresolved_fields=unresolved, max_col=max_col, column_map=mapping)

    lot_id_col = mapping.get("lot_id")
    if lot_id_col is None:
        result.anomalies.append(
            Anomaly(
                kind="critical",
                message=(
                    "Не найдена колонка с номером лота в файле Портала "
                    "(ожидалась колонка B)."
                ),
            )
        )
        return result

    sum_col = mapping.get("sum_no_vat")
    seen_keys: Dict[tuple, int] = {}

    for row_number, row in enumerate(
        ws.iter_rows(min_row=DATA_START_ROW, max_row=ws.max_row, max_col=max_col),
        start=DATA_START_ROW,
    ):
        row_values = {col: cell.value for col, cell in enumerate(row, start=1)}
        raw_lot_id = row_values.get(lot_id_col)

        if raw_lot_id is None or str(raw_lot_id).strip() == "":
            has_any_value = any(
                v is not None and str(v).strip() != "" for v in row_values.values()
            )
            if has_any_value and not _is_category_separator(row_values):
                result.anomalies.append(
                    Anomaly(
                        kind="row_without_lot_id",
                        message=f"Строка {row_number}: нет номера лота, строка пропущена.",
                        row_numbers=[row_number],
                    )
                )
            continue

        result.total_rows_read += 1
        identifier = parse_lot_number(raw_lot_id)
        if identifier.parse_error:
            result.anomalies.append(
                Anomaly(
                    kind="unparsable_lot_number",
                    message=f"Строка {row_number}: {identifier.parse_error}.",
                    row_numbers=[row_number],
                )
            )
            continue
        if identifier.missing_kind:
            result.anomalies.append(
                Anomaly(
                    kind="missing_kind",
                    message=(
                        f"Строка {row_number}: у лота '{identifier.raw}' не определен "
                        "вид закупки (Т/Р/У)."
                    ),
                    lot_key=identifier.key,
                    row_numbers=[row_number],
                )
            )

        if identifier.key in seen_keys:
            result.anomalies.append(
                Anomaly(
                    kind="duplicate_portal_lot",
                    message=(
                        f"Строка {row_number}: дублирующийся лот '{identifier.raw}' "
                        f"на Портале (первое вхождение - строка {seen_keys[identifier.key]})."
                    ),
                    lot_key=identifier.key,
                    row_numbers=[seen_keys[identifier.key], row_number],
                )
            )
        else:
            seen_keys[identifier.key] = row_number

        fields: Dict[str, object] = {}
        for canonical_field, col_idx in mapping.items():
            if canonical_field == "lot_id":
                continue
            fields[canonical_field] = row_values.get(col_idx)

        sum_raw = row_values.get(sum_col) if sum_col else None
        sum_value = to_float(sum_raw)
        fields["sum_no_vat"] = sum_value if sum_value is not None else 0.0

        record = LotRecord(
            source=Source.PORTAL,
            row_number=row_number,
            identifier=identifier,
            fields=fields,
            raw_row=row_values,
        )
        # При дублях сохраняем последнюю встреченную запись как актуальную.
        result.records = [
            r for r in result.records if r.identifier.key != identifier.key
        ]
        result.records.append(record)

    return result
