"""Лог запусков сверки (F10): дата, кол-во лотов по статусам, аномалии."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List

from lot_reconciler.models import ReconciliationReport

DEFAULT_HISTORY_PATH = Path(__file__).resolve().parent.parent / "history" / "runs.jsonl"


def log_run(
    report: ReconciliationReport,
    sap_filename: str,
    portal_filename: str,
    history_path: Path = DEFAULT_HISTORY_PATH,
) -> dict:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "sap_filename": sap_filename,
        "portal_filename": portal_filename,
        "sap_rows": report.sap_row_count,
        "portal_rows": report.portal_row_count,
        "counts_by_status": report.counts_by_status(),
        "anomaly_count": len(report.anomalies),
    }
    with open(history_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_history(history_path: Path = DEFAULT_HISTORY_PATH) -> List[dict]:
    if not history_path.exists():
        return []
    entries = []
    with open(history_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries
