from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from components.ui import money, show_error
from config.settings import settings
from models.entities import Account, Budget, Category, SavingsGoal
from services.finance import (FinanceError, budget_status, contribute_to_goal, create_budget,
                              create_goal, goal_progress)


MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def render(session: Session) -> None:
    st.title("Planificación")
    budgets_tab, goals_tab = st.tabs(["Presupuestos", "Objetivos de ahorro"])
    categories = session.scalars(select(Category).where(Category.kind == "expense").order_by(Category.name)).all()
    accounts = session.scalars(select(Account).where(Account.active.is_(True)).order_by(Account.name)).all()

    with budgets_tab:
        today = date.today()
        period_columns = st.columns(2)
        view_year = period_columns[0].selectbox("Consultar año", range(today.year, today.year - 10, -1), key="budget_view_year")
        view_month = period_columns[1].selectbox("Consultar mes", range(1, 13), index=today.month - 1,
                                                  format_func=lambda item: MONTHS[item - 1], key="budget_view_month")
        budgets = session.scalars(select(Budget).where(Budget.year == view_year, Budget.month == view_month)).all()
        with st.expander("Definir presupuesto mensual"):
            if not categories:
                st.info("Crea una categoría de gasto antes de presupuestar.")
            else:
                with st.form("create_budget"):
                    category = st.selectbox("Categoría", categories, format_func=lambda item: item.name)
                    year = st.number_input("Año", min_value=2000, max_value=2200, value=today.year, step=1)
                    month = st.selectbox("Mes", range(1, 13), index=today.month - 1, format_func=lambda item: MONTHS[item - 1])
                    amount = st.number_input(f"Límite ({settings.currency})", min_value=0.01, step=25.0, format="%.2f")
                    submitted = st.form_submit_button("Guardar presupuesto", type="primary")
                if submitted:
                    try:
                        create_budget(session, category.id, int(year), month, amount)
                        st.success("Presupuesto guardado.")
                        st.rerun()
                    except FinanceError as error:
                        show_error(error)
        if budgets:
            for budget in budgets:
                category = session.get(Category, budget.category_id)
                spent, percent = budget_status(session, budget)
                limit_amount = Decimal(budget.limit_amount)
                st.markdown(f"**{category.name if category else 'Categoría eliminada'}** · {money(spent, settings.currency)} de {money(limit_amount, settings.currency)}")
                st.progress(min(float(percent) / 100, 1.0))
                if percent >= 100:
                    st.warning(f"Has superado el límite en {money(spent - limit_amount, settings.currency)}.")
                elif percent >= 80:
                    st.info(f"Has utilizado el {percent:.0f}% del presupuesto.")
        else:
            st.caption("No hay presupuestos para este mes.")

    with goals_tab:
        goals = session.scalars(select(SavingsGoal).order_by(SavingsGoal.created_at.desc())).all()
        with st.expander("Crear objetivo de ahorro", expanded=not goals):
            with st.form("create_goal"):
                name = st.text_input("Objetivo", placeholder="Viaje, fondo de emergencia…")
                target = st.number_input(f"Cantidad objetivo ({settings.currency})", min_value=0.01, step=100.0, format="%.2f")
                deadline = st.date_input("Fecha límite (opcional)", value=None, format="DD/MM/YYYY")
                submitted = st.form_submit_button("Crear objetivo", type="primary")
            if submitted:
                try:
                    create_goal(session, name, target, deadline)
                    st.success("Objetivo creado.")
                    st.rerun()
                except FinanceError as error:
                    show_error(error)
        if goals:
            for goal in goals:
                total = goal_progress(session, goal)
                target = Decimal(goal.target_amount)
                st.markdown(f"**{goal.name}** · {money(total, settings.currency)} de {money(target, settings.currency)}")
                st.progress(min(float(total / target), 1.0))
                st.caption(f"{float(total / target * 100):.1f}% completado" + (f" · Fecha límite {goal.deadline:%d/%m/%Y}" if goal.deadline else ""))
            if accounts:
                with st.form("goal_contribution"):
                    goal = st.selectbox("Objetivo", goals, format_func=lambda item: item.name)
                    account = st.selectbox("Cuenta", accounts, format_func=lambda item: item.name)
                    amount = st.number_input(f"Aportación ({settings.currency})", min_value=0.01, step=25.0, format="%.2f")
                    contributed_on = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY", key="contribution_date")
                    note = st.text_input("Nota (opcional)")
                    submitted = st.form_submit_button("Registrar aportación")
                if submitted:
                    try:
                        contribute_to_goal(session, goal.id, account.id, amount, contributed_on, note)
                        st.success("Aportación registrada.")
                        st.rerun()
                    except FinanceError as error:
                        show_error(error)
        else:
            st.caption("Crea un objetivo para seguir tus aportaciones.")
