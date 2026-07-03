from automation.portal_common import get_ident, get_lot_number, get_reason, read_upload_rows
from tests.conftest import build_sap_workbook


def _build_upload_file(tmp_path):
    rows = [
        {
            "lot_id": "25/1 Т",
            "action_type_reference": "изменить",
            "isez_number": "10-1 Т",
        },
        {
            "lot_id": "25/2 Т",
            "action_type_reference": "исключить",
            "isez_number": "20-1 Т",
            "exclusion_reason": "в связи с корректировкой бюджета",
            "sum_no_vat": 1000,
        },
        {
            "lot_id": "25/3 Т",
            "action_type_reference": "добавить",
            "isez_number": "#N/A",
            "sum_no_vat": 1000,
        },
        {
            "lot_id": "25/4 Т",
            "action_type_reference": "исключить",
            "isez_number": "40-1 Т",
            "sum_no_vat": 1000,
        },  # без явной причины исключения
    ]
    buffer = build_sap_workbook(rows)
    path = tmp_path / "upload.xlsx"
    path.write_bytes(buffer.getvalue())
    return path


def test_read_upload_rows_filters_by_action(tmp_path):
    path = _build_upload_file(tmp_path)

    excluded = read_upload_rows(str(path), "исключить")
    assert {get_ident(lot) for lot in excluded} == {"25/2 Т", "25/4 Т"}

    changed = read_upload_rows(str(path), "изменить")
    assert {get_ident(lot) for lot in changed} == {"25/1 Т"}

    added = read_upload_rows(str(path), "добавить")
    assert {get_ident(lot) for lot in added} == {"25/3 Т"}


def test_get_lot_number_and_reason_defaults(tmp_path):
    path = _build_upload_file(tmp_path)
    lots = read_upload_rows(str(path), "исключить")
    by_ident = {get_ident(lot): lot for lot in lots}

    with_reason = by_ident["25/2 Т"]
    assert get_lot_number(with_reason) == "20-1 Т"
    assert get_reason(with_reason) == "в связи с корректировкой бюджета"

    without_reason = by_ident["25/4 Т"]
    assert get_lot_number(without_reason) == "40-1 Т"
    assert get_reason(without_reason) == "в связи с корректировкой бюджета"
