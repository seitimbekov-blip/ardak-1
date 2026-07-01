"""Вспомогательные функции для чтения Excel-файлов с многоуровневыми заголовками
и авто-поиском колонок по алиасам, когда точное положение колонки заранее не известно.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from openpyxl.utils import column_index_from_string
from openpyxl.worksheet.worksheet import Worksheet

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "field_aliases.json"


def load_field_config(config_path: Optional[Path] = None) -> dict:
    path = config_path or DEFAULT_CONFIG_PATH
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def normalize_header_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text


def build_combined_headers(
    ws: Worksheet, header_rows: Iterable[int], max_col: int
) -> Dict[int, str]:
    """Склеивает текст заголовков из нескольких строк (многоуровневая шапка)
    в одну строку на колонку, для последующего поиска по алиасам."""
    headers: Dict[int, List[str]] = {col: [] for col in range(1, max_col + 1)}
    for row in header_rows:
        for col in range(1, max_col + 1):
            value = ws.cell(row=row, column=col).value
            text = normalize_header_text(value)
            if text:
                headers[col].append(text)
    return {col: " ".join(parts) for col, parts in headers.items()}


def find_column_by_aliases(
    combined_headers: Dict[int, str], aliases: List[str]
) -> Optional[int]:
    for alias in aliases:
        alias_norm = normalize_header_text(alias)
        for col, text in combined_headers.items():
            if alias_norm and alias_norm in text:
                return col
    return None


def resolve_columns(
    ws: Worksheet,
    header_rows: Iterable[int],
    max_col: int,
    field_config: dict,
) -> Tuple[Dict[str, int], List[str]]:
    """Возвращает (маппинг канонического поля -> номер колонки (1-based), список
    полей, которые не удалось определить)."""
    combined_headers = build_combined_headers(ws, header_rows, max_col)
    mapping: Dict[str, int] = {}
    unresolved: List[str] = []

    for canonical_field, spec in field_config.items():
        column_idx: Optional[int] = None
        fixed_letter = spec.get("column")
        if fixed_letter:
            try:
                candidate = column_index_from_string(fixed_letter)
                if candidate <= max_col:
                    column_idx = candidate
            except ValueError:
                column_idx = None
        if column_idx is None:
            aliases = spec.get("aliases") or []
            column_idx = find_column_by_aliases(combined_headers, aliases)
        if column_idx is None:
            unresolved.append(canonical_field)
        else:
            mapping[canonical_field] = column_idx

    return mapping, unresolved


def worksheet_max_col_with_data(ws: Worksheet, sample_rows: int = 50) -> int:
    """Оценивает максимальную колонку с данными (ws.max_column иногда завышен)."""
    max_col = 1
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, sample_rows)):
        for cell in row:
            if cell.value is not None and cell.column > max_col:
                max_col = cell.column
    return max(max_col, ws.max_column if ws.max_column else max_col)
