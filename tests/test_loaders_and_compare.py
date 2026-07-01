from lot_reconciler.compare import reconcile
from lot_reconciler.models import LotStatus
from lot_reconciler.portal_loader import load_portal_file
from lot_reconciler.sap_loader import load_sap_file
from tests.conftest import BlankRow, Separator, build_portal_workbook, build_sap_workbook


def _base_lot(**overrides):
    lot = {
        "action_type_reference": "изменить",
        "month": "Январь",
        "quantity": 10,
        "unit_price": 100,
        "priority": "высокий",
        "method": "конкурс",
        "address": "г. Астана, ул. Мира 1",
        "sum_with_vat": 1120,
        "delivery_terms": "10 дней",
        "payment_terms": "предоплата",
        "sum_no_vat": 1000,
    }
    lot.update(overrides)
    return lot


def build_sample_files():
    sap_rows = [
        # 1. Новый лот - есть только в SAP -> ДОБАВИТЬ
        {"lot_id": "10/1 Т", **_base_lot()},
        # 2. Совпадает полностью с порталом -> БЕЗ ИЗМЕНЕНИЙ
        {"lot_id": "10/2 Т", **_base_lot()},
        # 3. Отличается месяц -> ИЗМЕНИТЬ
        {"lot_id": "10/3 Т", **_base_lot(month="Февраль")},
        # 4. Зануленная версия в SAP, лот есть на портале -> ИСКЛЮЧИТЬ + аномалия
        {"lot_id": "10/4 Т", **_base_lot(sum_no_vat=0)},
        # 5. Версионность: версия 0 занулена, версия 1 актуальна
        {"lot_id": "20/1 Р", **_base_lot(sum_no_vat=0)},
        {"lot_id": "20/1-1 Р", **_base_lot(sum_no_vat=500)},
        # 6. Несколько ненулевых версий -> аномалия, берём максимальную версию
        {"lot_id": "30/1 У", **_base_lot(sum_no_vat=100)},
        {"lot_id": "30/1-1 У", **_base_lot(sum_no_vat=200)},
        # 7. Все версии занулены -> аномалия "нет актуальной версии", нет на портале
        {"lot_id": "40/1 Т", **_base_lot(sum_no_vat=0)},
        {"lot_id": "40/1-1 Т", **_base_lot(sum_no_vat=0)},
        # 8. Нет вида закупки -> аномалия missing_kind
        {"lot_id": "50/1", **_base_lot(sum_no_vat=300)},
        # 9. Строка без номера лота, но с данными -> аномалия row_without_lot_id
        {"lot_id": None, **_base_lot(sum_no_vat=999)},
    ]
    sap_buffer = build_sap_workbook(sap_rows)

    portal_items = [
        Separator("1. Товары"),
        {"lot_id": "10/2 Т", **_base_lot()},
        {"lot_id": "10/3 Т", **_base_lot()},  # SAP has month=Февраль -> diff
        {"lot_id": "10/4 Т", **_base_lot()},  # исключить (SAP zeroed)
        BlankRow(),
        Separator("2. Работы"),
        {"lot_id": "20/1-1 Р", **_base_lot(sum_no_vat=500)},
        {"lot_id": "30/1-1 У", **_base_lot(sum_no_vat=200)},
        Separator("3. Услуги"),
    ]
    portal_buffer = build_portal_workbook(portal_items)
    return sap_buffer, portal_buffer


def test_full_reconciliation_scenarios():
    sap_buffer, portal_buffer = build_sample_files()

    sap_result = load_sap_file(sap_buffer)
    portal_result = load_portal_file(portal_buffer)

    # Строка без номера лота должна быть зафиксирована как аномалия и пропущена.
    assert any(a.kind == "row_without_lot_id" for a in sap_result.anomalies)

    report = reconcile(sap_result, portal_result)
    status_by_lot = {r.display_lot_number: r.status for r in report.results}

    assert status_by_lot["10/1 Т"] == LotStatus.ADD
    assert status_by_lot["10/2 Т"] == LotStatus.UNCHANGED
    assert status_by_lot["10/3 Т"] == LotStatus.CHANGE
    assert status_by_lot["10/4 Т"] == LotStatus.REMOVE
    assert status_by_lot["20/1-1 Р"] == LotStatus.UNCHANGED
    assert status_by_lot["30/1-1 У"] == LotStatus.UNCHANGED

    # Лот 40/1 полностью занулён и отсутствует на портале - не должен попасть в результаты.
    assert "40/1 Т" not in status_by_lot
    assert "40/1-1 Т" not in status_by_lot

    anomaly_kinds = {a.kind for a in report.anomalies}
    assert "no_actual_version" in anomaly_kinds
    assert "multiple_nonzero_versions" in anomaly_kinds
    assert "missing_kind" in anomaly_kinds
    assert "row_without_lot_id" in anomaly_kinds

    # Проверяем diff для изменённого лота.
    changed = next(r for r in report.results if r.display_lot_number == "10/3 Т")
    assert any(d.field == "month" for d in changed.diffs)

    # Category separator rows и пустая строка не должны создавать аномалий/записей.
    assert portal_result.total_rows_read == 5  # 10/2,10/3,10/4,20/1-1,30/1-1


def test_action_type_reference_is_informational_only():
    sap_buffer, portal_buffer = build_sample_files()
    sap_result = load_sap_file(sap_buffer)
    portal_result = load_portal_file(portal_buffer)
    report = reconcile(sap_result, portal_result)

    added = next(r for r in report.results if r.display_lot_number == "10/1 Т")
    # В тестовых данных action_type_reference = "изменить", но реальный статус - ДОБАВИТЬ.
    assert added.action_type_reference == "изменить"
    assert added.status == LotStatus.ADD
