"""Streamlit UI: сверка лотов плана закупок SAP <-> Портал закупок.

Запуск: streamlit run app.py
"""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import streamlit as st

from lot_reconciler.export import export_em_agent_file, export_full_report
from lot_reconciler.models import LotStatus
from lot_reconciler.history import read_history
from lot_reconciler.pipeline import run_reconciliation

st.set_page_config(page_title="Сверка лотов плана закупок", layout="wide")

STATUS_COLORS = {
    LotStatus.ADD.value: "#C6EFCE",
    LotStatus.CHANGE.value: "#FFEB9C",
    LotStatus.REMOVE.value: "#FFC7CE",
    LotStatus.UNCHANGED.value: "#FFFFFF",
}


def _format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _results_to_dataframe(results) -> pd.DataFrame:
    rows = []
    for r in results:
        sap_sum = r.sap_record.fields.get("sum_no_vat") if r.sap_record else None
        portal_sum = r.portal_record.fields.get("sum_no_vat") if r.portal_record else None
        diffs_text = "; ".join(
            f"{d.label}: было={_format_value(d.sap_value)} -> стало={_format_value(d.portal_value)}"
            for d in r.diffs
        )
        rows.append(
            {
                "Номер лота": r.display_lot_number,
                "Вид закупки": r.kind or "",
                "Статус": r.status.value,
                "Тип действия (SAP, справочно)": r.action_type_reference or "",
                "Сумма без НДС (SAP)": _format_value(sap_sum),
                "Сумма без НДС (Портал)": _format_value(portal_sum),
                "Изменённые поля (было -> стало)": diffs_text,
                "Строка SAP": r.sap_record.row_number if r.sap_record else "",
                "Строка Портал": r.portal_record.row_number if r.portal_record else "",
            }
        )
    return pd.DataFrame(rows)


def _style_status(df: pd.DataFrame):
    def highlight(row):
        color = STATUS_COLORS.get(row["Статус"], "#FFFFFF")
        return [f"background-color: {color}"] * len(row)

    return df.style.apply(highlight, axis=1)


st.title("Сверка и заливка лотов плана закупок")
st.caption(
    "Сравнение выгрузки SAP и выгрузки с Портала закупок, автоматический расчёт "
    "статуса каждого лота (ДОБАВИТЬ / ИЗМЕНИТЬ / ИСКЛЮЧИТЬ / БЕЗ ИЗМЕНЕНИЙ) и "
    "подготовка файла для em_agent.py."
)

tab_compare, tab_history = st.tabs(["Сверка", "История запусков"])

with tab_compare:
    col1, col2 = st.columns(2)
    with col1:
        sap_file = st.file_uploader("Выгрузка из SAP (.xlsx)", type=["xlsx"], key="sap_file")
    with col2:
        portal_file = st.file_uploader(
            "Выгрузка с Портала закупок / ИСЭЗ 2.0 (.xlsx)", type=["xlsx"], key="portal_file"
        )

    if st.button("Сравнить", type="primary", disabled=not (sap_file and portal_file)):
        with st.spinner("Сверяем лоты..."):
            try:
                sap_bytes = io.BytesIO(sap_file.getvalue())
                portal_bytes = io.BytesIO(portal_file.getvalue())
                pipeline_result = run_reconciliation(
                    sap_bytes,
                    portal_bytes,
                    sap_filename=sap_file.name,
                    portal_filename=portal_file.name,
                )
                st.session_state["pipeline_result"] = pipeline_result
            except Exception as exc:  # noqa: BLE001 - показываем пользователю причину сбоя
                st.session_state.pop("pipeline_result", None)
                st.error(f"Не удалось выполнить сверку: {exc}")

    pipeline_result = st.session_state.get("pipeline_result")
    if pipeline_result is not None:
        report = pipeline_result.report
        counts = report.counts_by_status()

        st.subheader("Итоги сверки")
        metric_cols = st.columns(4)
        for col, status in zip(metric_cols, LotStatus):
            col.metric(status.value, counts.get(status.value, 0))

        if report.anomalies:
            with st.expander(f"Аномалии, требующие внимания ({len(report.anomalies)})", expanded=False):
                anomaly_rows = [
                    {
                        "Тип": a.kind,
                        "Сообщение": a.message,
                        "Лот": f"{a.lot_key[0]} {a.lot_key[1] or ''}".strip() if a.lot_key else "",
                        "Строки": ", ".join(str(r) for r in a.row_numbers),
                    }
                    for a in report.anomalies
                ]
                st.dataframe(pd.DataFrame(anomaly_rows), use_container_width=True)
        else:
            st.success("Аномалий не обнаружено.")

        st.subheader("Результаты сверки")
        status_filter = st.multiselect(
            "Фильтр по статусу",
            options=[s.value for s in LotStatus],
            default=[s.value for s in LotStatus],
        )
        filtered_results = [r for r in report.results if r.status.value in status_filter]
        df = _results_to_dataframe(filtered_results)
        st.dataframe(_style_status(df), use_container_width=True, height=500)

        st.subheader("Экспорт")
        full_report_buffer = io.BytesIO()
        export_full_report(report, full_report_buffer)
        full_report_buffer.seek(0)

        em_agent_buffer = io.BytesIO()
        export_em_agent_file(report, pipeline_result.sap_result, em_agent_buffer)
        em_agent_buffer.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            st.download_button(
                "Скачать полный отчёт (с подсветкой)",
                data=full_report_buffer,
                file_name=f"sverka_lotov_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with dl_col2:
            st.download_button(
                "Скачать файл для em_agent.py",
                data=em_agent_buffer,
                file_name=f"em_agent_input_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    else:
        st.info("Загрузите оба файла и нажмите «Сравнить».")

with tab_history:
    history = read_history()
    if not history:
        st.info("История запусков пока пуста.")
    else:
        history_rows = []
        for entry in reversed(history):
            row = {
                "Дата": entry["timestamp"],
                "Файл SAP": entry["sap_filename"],
                "Файл Портала": entry["portal_filename"],
                "Строк SAP": entry["sap_rows"],
                "Строк Портала": entry["portal_rows"],
                "Аномалий": entry["anomaly_count"],
            }
            row.update(entry["counts_by_status"])
            history_rows.append(row)
        st.dataframe(pd.DataFrame(history_rows), use_container_width=True)
