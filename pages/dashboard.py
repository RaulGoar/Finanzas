from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from components.ui import format_date_es, money
from config.settings import settings
from models.entities import Account, Category, NetWorthSnapshot, Transaction
from services.finance import account_balances, net_worth, save_net_worth_snapshot


def render(session: Session) -> None:
    today = date.today()
    month_start = today.replace(day=1)
    st.title("Resumen")
    st.caption(format_date_es(today, include_weekday=True))

    records = session.execute(
        select(Transaction, Account.name, Category.name)
        .join(Account, Transaction.account_id == Account.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.occurred_on >= month_start, Transaction.occurred_on <= today)
    ).all()
    income = sum((Decimal(row[0].amount) for row in records if row[0].kind == "income"), Decimal("0"))
    expenses = sum((Decimal(row[0].amount) for row in records if row[0].kind == "expense"), Decimal("0"))
    savings = income - expenses
    savings_rate = float(savings / income * 100) if income else 0
    balances = account_balances(session)
    total_balance = sum(balances.values(), Decimal("0"))
    worth = net_worth(session)

    columns = st.columns(4)
    columns[0].metric("Patrimonio neto", money(worth, settings.currency))
    columns[1].metric("Saldo en cuentas", money(total_balance, settings.currency))
    columns[2].metric("Ingresos del mes", money(income, settings.currency))
    columns[3].metric("Gastos del mes", money(expenses, settings.currency))
    columns = st.columns(2)
    columns[0].metric("Ahorro del mes", money(savings, settings.currency))
    columns[1].metric("Tasa de ahorro", f"{savings_rate:.1f}%")

    st.divider()
    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Ingresos y gastos")
        all_transactions = session.scalars(select(Transaction).where(Transaction.kind.in_(["income", "expense"]))).all()
        if all_transactions:
            frame = pd.DataFrame([{"Fecha": item.occurred_on, "Tipo": "Ingresos" if item.kind == "income" else "Gastos",
                                   "Importe": float(item.amount)} for item in all_transactions])
            frame["Mes"] = pd.to_datetime(frame["Fecha"]).dt.to_period("M").dt.to_timestamp()
            monthly = frame.groupby(["Mes", "Tipo"], as_index=False)["Importe"].sum()
            chart = px.bar(monthly, x="Mes", y="Importe", color="Tipo", barmode="group",
                           color_discrete_map={"Ingresos": "#4E8B69", "Gastos": "#C26D4A"})
            chart.update_layout(margin=dict(l=0, r=0, t=16, b=0), legend_title_text="", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(chart, width="stretch")
        else:
            st.info("Añade tu primer movimiento para ver la comparativa mensual.")

    with right:
        st.subheader("Gastos por categoría")
        expenses_by_category = [(category or "Sin categoría", amount) for category, amount in
                                _category_expenses(records)]
        if expenses_by_category:
            chart = px.pie(pd.DataFrame(expenses_by_category, columns=["Categoría", "Importe"]),
                           names="Categoría", values="Importe", hole=.58,
                           color_discrete_sequence=["#3F765E", "#C26D4A", "#6687A3", "#C39A4B", "#B86F78", "#9A7BA8"])
            chart.update_layout(margin=dict(l=0, r=0, t=16, b=0), paper_bgcolor="rgba(0,0,0,0)", legend_title_text="")
            st.plotly_chart(chart, width="stretch")
        else:
            st.info("Este mes todavía no hay gastos registrados.")

    st.divider()
    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Evolución del patrimonio")
        snapshots = session.scalars(select(NetWorthSnapshot).order_by(NetWorthSnapshot.captured_on)).all()
        if snapshots:
            frame = pd.DataFrame([{"Fecha": item.captured_on, "Patrimonio": float(item.net_worth)} for item in snapshots])
            chart = px.line(frame, x="Fecha", y="Patrimonio", markers=True, color_discrete_sequence=["#3F765E"])
            chart.update_layout(margin=dict(l=0, r=0, t=16, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(chart, width="stretch")
        else:
            st.caption("Registra cortes periódicos para seguir cómo evoluciona tu patrimonio.")
        if st.button("Guardar valoración de hoy", icon=":material/bookmark_add:"):
            save_net_worth_snapshot(session, today)
            st.success("Valoración guardada.")
            st.rerun()

    with right:
        st.subheader("Cuentas")
        accounts = session.scalars(select(Account).where(Account.active.is_(True)).order_by(Account.name)).all()
        if accounts:
            st.dataframe(pd.DataFrame([{"Cuenta": account.name, "Tipo": account.account_type,
                                       "Saldo": money(balances.get(account.id, Decimal("0")), settings.currency)}
                                      for account in accounts]), hide_index=True, width="stretch")
        else:
            st.info("Crea una cuenta para empezar a registrar tus finanzas.")


def _category_expenses(records) -> list[tuple[str, float]]:
    totals: dict[str, float] = {}
    for transaction, _account_name, category_name in records:
        if transaction.kind == "expense":
            label = category_name or "Sin categoría"
            totals[label] = totals.get(label, 0) + float(transaction.amount)
    return sorted(totals.items(), key=lambda pair: pair[1], reverse=True)
