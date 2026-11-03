from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from components.ui import money
from config.settings import settings
from models.entities import Category, NetWorthSnapshot, Transaction

MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def render(session: Session) -> None:
    st.title("Informes")
    today = date.today()
    year = st.selectbox("Año", list(range(today.year, today.year - 10, -1)), key="report_year")
    period = st.radio("Periodo", ["Mensual", "Anual"], horizontal=True)
    month = st.selectbox("Mes", range(1, 13), index=today.month - 1, format_func=lambda value: MONTHS[value - 1]) if period == "Mensual" else None
    transactions = session.scalars(select(Transaction).where(Transaction.kind.in_(["income", "expense"]),
                                                               Transaction.occurred_on >= date(year, month or 1, 1),
                                                               Transaction.occurred_on < _period_end(year, month))).all()
    categories = {item.id: item.name for item in session.scalars(select(Category))}
    frame = pd.DataFrame([{"Fecha": item.occurred_on, "Tipo": "Ingreso" if item.kind == "income" else "Gasto",
                           "Descripción": item.description, "Categoría": categories.get(item.category_id, "Sin categoría"),
                           "Importe": float(item.amount)} for item in transactions])
    income = sum((Decimal(item.amount) for item in transactions if item.kind == "income"), Decimal("0"))
    expenses = sum((Decimal(item.amount) for item in transactions if item.kind == "expense"), Decimal("0"))
    savings = income - expenses
    previous_year, previous_month = _previous_period(year, month)
    previous_transactions = session.scalars(select(Transaction).where(
        Transaction.kind.in_(["income", "expense"]),
        Transaction.occurred_on >= date(previous_year, previous_month or 1, 1),
        Transaction.occurred_on < _period_end(previous_year, previous_month))).all()
    previous_income = sum((Decimal(item.amount) for item in previous_transactions if item.kind == "income"), Decimal("0"))
    previous_expenses = sum((Decimal(item.amount) for item in previous_transactions if item.kind == "expense"), Decimal("0"))
    previous_savings = previous_income - previous_expenses
    columns = st.columns(3)
    columns[0].metric("Ingresos", money(income, settings.currency))
    columns[1].metric("Gastos", money(expenses, settings.currency))
    columns[2].metric("Ahorro", money(savings, settings.currency))

    comparison_label = f"{MONTHS[previous_month - 1]} {previous_year}" if previous_month else str(previous_year)
    st.subheader(f"Comparativa con {comparison_label}")
    comparison = st.columns(3)
    for column, label, current, previous in zip(
        comparison,
        ["Ingresos", "Gastos", "Ahorro"],
        [income, expenses, savings],
        [previous_income, previous_expenses, previous_savings],
    ):
        difference = current - previous
        delta = ("+" if difference >= 0 else "−") + money(abs(difference), settings.currency)
        column.metric(f"Variación de {label.lower()}", money(current, settings.currency), delta)

    left, right = st.columns(2)
    with left:
        st.subheader("Balance por categoría")
        if not frame.empty:
            expenses_frame = frame[frame["Tipo"] == "Gasto"].groupby("Categoría", as_index=False)["Importe"].sum()
            if not expenses_frame.empty:
                chart = px.bar(expenses_frame.sort_values("Importe"), x="Importe", y="Categoría", orientation="h",
                               color_discrete_sequence=["#C26D4A"])
                chart.update_layout(margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(chart, width="stretch")
            else:
                st.caption("No hay gastos en el periodo.")
        else:
            st.caption("No hay movimientos en el periodo.")
    with right:
        st.subheader("Movimientos del periodo")
        if not frame.empty:
            display_frame = frame.assign(Fecha=pd.to_datetime(frame["Fecha"]).dt.strftime("%d/%m/%Y"))
            st.dataframe(display_frame, hide_index=True, width="stretch")
        else:
            st.caption("No hay movimientos en el periodo.")

    if period == "Anual":
        year_transactions = session.scalars(select(Transaction).where(
            Transaction.kind.in_(["income", "expense"]),
            Transaction.occurred_on >= date(year, 1, 1),
            Transaction.occurred_on < date(year + 1, 1, 1))).all()
        if year_transactions:
            yearly = pd.DataFrame([{"Mes": item.occurred_on.month,
                                    "Tipo": item.kind,
                                    "Importe": float(item.amount)} for item in year_transactions])
            grouped = yearly.pivot_table(index="Mes", columns="Tipo", values="Importe", aggfunc="sum", fill_value=0)
            grouped = grouped.reindex(range(1, 13), fill_value=0)
            income_months = grouped.get("income", pd.Series(0, index=grouped.index))
            expense_months = grouped.get("expense", pd.Series(0, index=grouped.index))
            savings_frame = pd.DataFrame({"Mes": [MONTHS[item - 1] for item in grouped.index],
                                          "Ahorro": income_months.values - expense_months.values})
            st.subheader("Evolución del ahorro")
            chart = px.bar(savings_frame, x="Mes", y="Ahorro", color_discrete_sequence=["#3F765E"])
            chart.update_layout(margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(chart, width="stretch")

    snapshots = session.scalars(select(NetWorthSnapshot).order_by(NetWorthSnapshot.captured_on)).all()
    if snapshots:
        snapshot_frame = pd.DataFrame([{"Fecha": item.captured_on, "Patrimonio": float(item.net_worth)} for item in snapshots])
        st.subheader("Evolución del patrimonio")
        chart = px.line(snapshot_frame, x="Fecha", y="Patrimonio", markers=True, color_discrete_sequence=["#6687A3"])
        chart.update_layout(margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(chart, width="stretch")

    if not frame.empty:
        export_frame = frame.assign(Fecha=pd.to_datetime(frame["Fecha"]).dt.strftime("%Y-%m-%d"), Moneda=settings.currency)
        csv_bytes = export_frame.to_csv(index=False).encode("utf-8-sig")
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            export_frame.to_excel(writer, index=False, sheet_name="Movimientos")
            pd.DataFrame([{"Ingresos": float(income), "Gastos": float(expenses), "Ahorro": float(savings),
                           "Moneda": settings.currency}]).to_excel(writer, index=False, sheet_name="Resumen")
        c1, c2 = st.columns(2)
        c1.download_button("Descargar CSV", csv_bytes, "informe_financiero.csv", "text/csv", icon=":material/download:")
        c2.download_button("Descargar Excel", excel_buffer.getvalue(), "informe_financiero.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/download:")


def _period_end(year: int, month: int | None) -> date:
    if month is None:
        return date(year + 1, 1, 1)
    return date(year + (month == 12), month % 12 + 1, 1)


def _previous_period(year: int, month: int | None) -> tuple[int, int | None]:
    if month is None:
        return year - 1, None
    if month == 1:
        return year - 1, 12
    return year, month - 1
