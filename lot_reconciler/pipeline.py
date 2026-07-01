"""Связывает загрузку файлов, сверку, экспорт и логирование в одну функцию,
используемую как из Streamlit UI, так и из CLI/тестов."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

from lot_reconciler.compare import reconcile
from lot_reconciler.history import log_run
from lot_reconciler.models import ReconciliationReport
from lot_reconciler.portal_loader import load_portal_file
from lot_reconciler.sap_loader import SapLoadResult, load_sap_file


@dataclass
class PipelineResult:
    report: ReconciliationReport
    sap_result: SapLoadResult


def run_reconciliation(
    sap_path_or_buffer: Union[str, Path, object],
    portal_path_or_buffer: Union[str, Path, object],
    *,
    sap_filename: str = "",
    portal_filename: str = "",
    write_history: bool = True,
) -> PipelineResult:
    sap_result = load_sap_file(sap_path_or_buffer)
    portal_result = load_portal_file(portal_path_or_buffer)
    report = reconcile(sap_result, portal_result)

    if write_history:
        log_run(report, sap_filename or str(sap_path_or_buffer), portal_filename or str(portal_path_or_buffer))

    return PipelineResult(report=report, sap_result=sap_result)
