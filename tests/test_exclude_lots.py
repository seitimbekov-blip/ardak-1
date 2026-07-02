import io

from openpyxl import Workbook

from automation.exclude_lots import get_lot_number, get_reason, read_lots_to_exclude


def _build_upload_file(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Форма плана закупок ... на ____ год"])
    ws.append([])
    ws.append([])
    ws.append(
        [
            "Идентификатор из внешней системы",
            "Номенклатурный код заказчика",
            "Тип действия",
            "Причина исключения",
            "№",
        ]
    )
    ws.append([])
    ws.append([])
    ws.append(["1", "2", "3", "4", "5"])
    ws.append(["25/1 Т", None, "изменить", None, "10-1 Т"])
    ws.append(["25/2 Т", None, "исключить", "в связи с корректировкой бюджета", "20-1 Т"])
    ws.append(["25/3 Т", None, "добавить", None, "#N/A"])
    ws.append(["25/4 Т", None, "исключить", None, "40-1 Т"])  # без явной причины

    path = tmp_path / "upload.xlsx"
    wb.save(path)
    return path


def test_read_lots_to_exclude_filters_by_action(tmp_path):
    path = _build_upload_file(tmp_path)
    lots = read_lots_to_exclude(str(path))
    assert len(lots) == 2
    idents = {lot["Идентификатор из внешней системы"] for lot in lots}
    assert idents == {"25/2 Т", "25/4 Т"}


def test_get_lot_number_and_reason_defaults(tmp_path):
    path = _build_upload_file(tmp_path)
    lots = read_lots_to_exclude(str(path))
    by_ident = {lot["Идентификатор из внешней системы"]: lot for lot in lots}

    with_reason = by_ident["25/2 Т"]
    assert get_lot_number(with_reason) == "20-1 Т"
    assert get_reason(with_reason) == "в связи с корректировкой бюджета"

    without_reason = by_ident["25/4 Т"]
    assert get_lot_number(without_reason) == "40-1 Т"
    assert get_reason(without_reason) == "в связи с корректировкой бюджета"
