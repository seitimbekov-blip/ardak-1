"""Загрузка выгрузки из SAP.

Структура (см. PRD, раздел 5):
- Заголовки на строках 4-6, данные - со строки 8.
- Колонка A - номер лота ("Идентификатор из внешней системы").
- Колонка B - "Тип действия" (справочно, не используется в логике расчета - F6a).
- Колонка AE - сумма без НДС на плановый год.
- Файл содержит все лоты, включая устаревшие/занулённые версии.
"""
from __future__ import annotations

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

HEADER_ROWS = [4, 5, 6]
# Реальные выгрузки иногда содержат строку с числовыми номерами колонок (1,2,3,...)
# сразу после заголовков (перед первой строкой данных) - она автоматически
# отбрасывается как аномалия "нет номера лота", поэтому старт сразу после
# заголовков надежнее жестко заданной строки 8.
DATA_START_ROW = 7


@dataclass
class SapLoadResult:
    records: List[LotRecord] = field(default_factory=list)
    anomalies: List[Anomaly] = field(default_factory=list)
    unresolved_fields: List[str] = field(default_factory=list)
    header_rows_values: List[List] = field(default_factory=list)
    column_map: Dict[str, int] = field(default_factory=dict)
    max_col: int = 0
    total_rows_read: int = 0


def load_sap_file(
    path_or_buffer: Union[str, Path, object],
    field_config: dict = None,
) -> SapLoadResult:
    config = field_config or load_field_config()["sap"]
    wb = load_workbook(path_or_buffer, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    max_col = worksheet_max_col_with_data(ws)

    mapping, unresolved = resolve_columns(ws, HEADER_ROWS, max_col, config)
    result = SapLoadResult(unresolved_fields=unresolved, max_col=max_col, column_map=mapping)

    lot_id_col = mapping.get("lot_id")
    if lot_id_col is None:
        result.anomalies.append(
            Anomaly(
                kind="critical",
                message=(
                    "Не найдена колонка с номером лота в SAP-файле "
                    "(ожидалась колонка A)."
                ),
            )
        )
        return result

    action_col = mapping.get("action_type_reference")
    sum_col = mapping.get("sum_no_vat")

    header_rows_values: List[List] = []
    for row_idx in HEADER_ROWS:
        header_rows_values.append(
            [ws.cell(row=row_idx, column=c).value for c in range(1, max_col + 1)]
        )
    result.header_rows_values = header_rows_values

    for row_number, row in enumerate(
        ws.iter_rows(min_row=DATA_START_ROW, max_row=ws.max_row, max_col=max_col),
        start=DATA_START_ROW,
    ):
        row_values = {col: cell.value for col, cell in enumerate(row, start=1)}
        raw_lot_id = row_values.get(lot_id_col)

        if raw_lot_id is None or str(raw_lot_id).strip() == "":
            # Полностью пустая строка (либо строка без номера лота) - пропускаем.
            if any(v is not None and str(v).strip() != "" for v in row_values.values()):
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

        fields: Dict[str, object] = {}
        for canonical_field, col_idx in mapping.items():
            if canonical_field in ("lot_id", "action_type_reference"):
                continue
            fields[canonical_field] = row_values.get(col_idx)

        sum_raw = row_values.get(sum_col) if sum_col else None
        sum_value = to_float(sum_raw)
        fields["sum_no_vat"] = sum_value if sum_value is not None else 0.0

        action_type_reference = row_values.get(action_col) if action_col else None

        record = LotRecord(
            source=Source.SAP,
            row_number=row_number,
            identifier=identifier,
            fields=fields,
            raw_row=row_values,
            action_type_reference=(
                str(action_type_reference).strip() if action_type_reference else None
            ),
        )
        result.records.append(record)

    return result
