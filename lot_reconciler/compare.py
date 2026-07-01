"""Сопоставление лотов SAP <-> Портал и определение статуса (F5, F6, F7)."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from lot_reconciler.models import (
    ALL_COMPARE_FIELDS,
    Anomaly,
    ComparisonResult,
    FIELD_LABELS,
    FieldDiff,
    LotRecord,
    LotStatus,
    ReconciliationReport,
)
from lot_reconciler.numeric_utils import to_float, values_equal
from lot_reconciler.portal_loader import PortalLoadResult
from lot_reconciler.sap_loader import SapLoadResult

_ZERO_TOLERANCE = 0.01


def _select_actual_sap_versions(
    sap_records: List[LotRecord],
) -> tuple[Dict[tuple, LotRecord], List[Anomaly]]:
    """Для каждого базового лота выбирает актуальную версию (сумма без НДС != 0).

    При нескольких ненулевых версиях берётся максимальная версия, с флагом
    для ручной проверки. Если ни одна версия не ненулевая - лот считается
    неактуальным (аномалия, актуальная запись отсутствует).
    """
    groups: Dict[tuple, List[LotRecord]] = defaultdict(list)
    for record in sap_records:
        key = record.identifier.key
        if key is None:
            continue
        groups[key].append(record)

    actuals: Dict[tuple, LotRecord] = {}
    anomalies: List[Anomaly] = []

    for key, records in groups.items():
        nonzero = [
            r for r in records if abs(to_float(r.fields.get("sum_no_vat")) or 0.0) > _ZERO_TOLERANCE
        ]
        if not nonzero:
            anomalies.append(
                Anomaly(
                    kind="no_actual_version",
                    message=(
                        f"Лот '{key[0]} {key[1] or ''}'".strip()
                        + ": все версии в SAP имеют нулевую сумму без НДС, "
                        "актуальная версия не определена."
                    ),
                    lot_key=key,
                    row_numbers=[r.row_number for r in records],
                )
            )
            continue

        if len(nonzero) > 1:
            versions = sorted({r.identifier.version for r in nonzero})
            anomalies.append(
                Anomaly(
                    kind="multiple_nonzero_versions",
                    message=(
                        f"Лот '{key[0]} {key[1] or ''}'".strip()
                        + f": найдено {len(nonzero)} версий с ненулевой суммой без НДС "
                        f"(версии: {versions}). Взята максимальная версия, "
                        "требуется ручная проверка."
                    ),
                    lot_key=key,
                    row_numbers=[r.row_number for r in nonzero],
                )
            )

        actual = max(nonzero, key=lambda r: r.identifier.version)
        actuals[key] = actual

    return actuals, anomalies


def _compare_records(sap_rec: LotRecord, portal_rec: LotRecord) -> List[FieldDiff]:
    diffs: List[FieldDiff] = []
    for field_name in ALL_COMPARE_FIELDS:
        if field_name not in sap_rec.fields or field_name not in portal_rec.fields:
            continue
        sap_value = sap_rec.fields.get(field_name)
        portal_value = portal_rec.fields.get(field_name)
        if not values_equal(sap_value, portal_value):
            diffs.append(
                FieldDiff(
                    field=field_name,
                    label=FIELD_LABELS.get(field_name, field_name),
                    sap_value=sap_value,
                    portal_value=portal_value,
                )
            )
    return diffs


def reconcile(
    sap_result: SapLoadResult, portal_result: PortalLoadResult
) -> ReconciliationReport:
    sap_actuals, version_anomalies = _select_actual_sap_versions(sap_result.records)
    portal_map: Dict[tuple, LotRecord] = {
        r.identifier.key: r for r in portal_result.records if r.identifier.key is not None
    }

    all_keys = set(sap_actuals) | set(portal_map)
    results: List[ComparisonResult] = []

    for key in sorted(all_keys, key=lambda k: (k[0], k[1] or "")):
        sap_rec = sap_actuals.get(key)
        portal_rec = portal_map.get(key)

        if sap_rec is not None and portal_rec is None:
            results.append(
                ComparisonResult(
                    lot_key=key, status=LotStatus.ADD, sap_record=sap_rec, portal_record=None
                )
            )
        elif portal_rec is not None and sap_rec is None:
            results.append(
                ComparisonResult(
                    lot_key=key,
                    status=LotStatus.REMOVE,
                    sap_record=None,
                    portal_record=portal_rec,
                )
            )
        else:
            diffs = _compare_records(sap_rec, portal_rec)
            status = LotStatus.CHANGE if diffs else LotStatus.UNCHANGED
            results.append(
                ComparisonResult(
                    lot_key=key,
                    status=status,
                    sap_record=sap_rec,
                    portal_record=portal_rec,
                    diffs=diffs,
                )
            )

    anomalies: List[Anomaly] = []
    anomalies.extend(sap_result.anomalies)
    anomalies.extend(portal_result.anomalies)
    anomalies.extend(version_anomalies)

    if sap_result.unresolved_fields:
        anomalies.append(
            Anomaly(
                kind="unresolved_sap_columns",
                message=(
                    "В SAP-файле не удалось автоматически определить колонки для полей: "
                    + ", ".join(FIELD_LABELS.get(f, f) for f in sap_result.unresolved_fields)
                    + ". Эти поля не участвуют в сравнении. При необходимости уточните "
                    "маппинг в config/field_aliases.json."
                ),
            )
        )
    if portal_result.unresolved_fields:
        anomalies.append(
            Anomaly(
                kind="unresolved_portal_columns",
                message=(
                    "В файле Портала не удалось автоматически определить колонки для полей: "
                    + ", ".join(
                        FIELD_LABELS.get(f, f) for f in portal_result.unresolved_fields
                    )
                    + ". Эти поля не участвуют в сравнении. При необходимости уточните "
                    "маппинг в config/field_aliases.json."
                ),
            )
        )

    return ReconciliationReport(
        results=results,
        anomalies=anomalies,
        sap_row_count=sap_result.total_rows_read,
        portal_row_count=portal_result.total_rows_read,
    )
