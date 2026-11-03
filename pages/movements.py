from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from components.ui import money, show_error
from config.settings import settings
from models.entities import Account, Category, RecurringRule, Transaction
from services.finance import (FinanceError, create_category, create_recurring_rule, create_transaction,
                              delete_transaction, process_recurring_rules, set_recurring_rule_active,
                              update_transaction)


KINDS = {"Gasto": "expense", "Ingreso": "income"}


def render(session: Session) -> None:
    st.title("Ingresos y gastos")
    accounts = session.scalars(select(Account).where(Account.active.is_(True)).order_by(Account.name)).all()
    categories = session.scalars(select(Category).order_by(Category.name)).all()
    tab_add, tab_list, tab_categories, tab_recurring = st.tabs(["Nuevo movimiento", "Movimientos", "Categorías", "Recurrentes"])

    with tab_add:
        if not accounts:
            st.info("Primero crea una cuenta en la sección Cuentas.")
        else:
            with st.form("new_transaction"):
                kind_label = st.segmented_control("Tipo", list(KINDS), default="Gasto", key="new_kind")
                kind = KINDS[kind_label]
                eligible = [item for item in categories if item.kind == kind]
                account = st.selectbox("Cuenta", accounts, format_func=lambda item: item.name, key="new_account")
                category = st.selectbox("Categoría", eligible, format_func=lambda item: item.name,
                                        index=None, placeholder="Sin categoría", key="new_category")
                description = st.text_input("Descripción", max_chars=180)
                amount = st.number_input(f"Importe ({settings.currency})", min_value=0.01, step=10.0, format="%.2f")
                occurred_on = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY", key="new_date")
                recurring = st.checkbox("Movimiento recurrente")
                notes = st.text_input("Notas (opcional)")
                submitted = st.form_submit_button("Guardar movimiento", type="primary")
            if submitted:
                try:
                    create_transaction(session, account_id=account.id, category_id=category.id if category else None,
                                       kind=kind, description=description, amount=amount, occurred_on=occurred_on,
                                       recurring=recurring, notes=notes)
                    st.success("Movimiento guardado.")
                    st.rerun()
                except FinanceError as error:
                    show_error(error)

    with tab_list:
        transactions = session.scalars(select(Transaction).where(Transaction.kind.in_(["income", "expense"]))
                                       .order_by(Transaction.occurred_on.desc(), Transaction.id.desc())).all()
        account_map = {item.id: item.name for item in accounts}
        category_map = {item.id: item.name for item in categories}
        f1, f2, f3 = st.columns(3)
        query = f1.text_input("Buscar descripción", key="filter_query").strip().lower()
        account_filter = f2.selectbox("Cuenta", ["Todas"] + [item.name for item in accounts], key="filter_account")
        category_filter = f3.selectbox("Categoría", ["Todas"] + [item.name for item in categories], key="filter_category")
        date_filter = st.date_input("Periodo", value=(date(date.today().year, 1, 1), date.today()),
                                    format="DD/MM/YYYY", key="filter_dates")
        start, end = date_filter if len(date_filter) == 2 else (date_filter[0], date_filter[0])
        selected = [item for item in transactions
                    if start <= item.occurred_on <= end
                    and (not query or query in item.description.lower())
                    and (account_filter == "Todas" or account_map.get(item.account_id) == account_filter)
                    and (category_filter == "Todas" or category_map.get(item.category_id) == category_filter)]
        table = pd.DataFrame([{"ID": item.id, "Fecha": item.occurred_on.strftime("%d/%m/%Y"),
                               "Descripción": item.description, "Tipo": "Ingreso" if item.kind == "income" else "Gasto",
                               "Categoría": category_map.get(item.category_id, "Sin categoría"),
                               "Cuenta": account_map.get(item.account_id, "—"),
                               "Importe": money(item.amount, settings.currency),
                               "Recurrente": "Sí" if item.recurring else "No"} for item in selected])
        st.dataframe(table, hide_index=True, width="stretch")
        if selected:
            csv = pd.DataFrame([{"Fecha": item.occurred_on.isoformat(), "Descripción": item.description,
                                 "Tipo": item.kind, "Categoría": category_map.get(item.category_id, ""),
                                 "Cuenta": account_map.get(item.account_id, ""), "Importe": str(item.amount),
                                 "Moneda": settings.currency} for item in selected]).to_csv(index=False).encode("utf-8-sig")
            st.download_button("Exportar selección a CSV", csv, "movimientos.csv", "text/csv", icon=":material/download:")
            with st.expander("Editar o eliminar"):
                chosen = st.selectbox("Movimiento", selected, format_func=lambda item: f"{item.occurred_on:%d/%m/%Y} · {item.description} · {money(item.amount, settings.currency)}", key="edit_tx_select")
                with st.form("edit_transaction"):
                    kind_label = st.selectbox("Tipo", list(KINDS), index=list(KINDS.values()).index(chosen.kind), key="edit_kind")
                    kind = KINDS[kind_label]
                    eligible = [item for item in categories if item.kind == kind]
                    account = st.selectbox("Cuenta", accounts, index=next((i for i, item in enumerate(accounts) if item.id == chosen.account_id), 0), format_func=lambda item: item.name, key="edit_account")
                    category_options = [None] + eligible
                    category_index = next((i + 1 for i, item in enumerate(eligible) if item.id == chosen.category_id), 0)
                    category = st.selectbox("Categoría", category_options, index=category_index,
                                            format_func=lambda item: item.name if item else "Sin categoría", key="edit_category")
                    description = st.text_input("Descripción", value=chosen.description, key="edit_description")
                    amount = st.number_input(f"Importe ({settings.currency})", min_value=0.01, value=float(chosen.amount), step=10.0, format="%.2f", key="edit_amount")
                    occurred_on = st.date_input("Fecha", value=chosen.occurred_on, format="DD/MM/YYYY", key="edit_date")
                    recurring = st.checkbox("Movimiento recurrente", value=chosen.recurring, key="edit_recurring")
                    save = st.form_submit_button("Guardar cambios", type="primary")
                if save:
                    try:
                        update_transaction(session, chosen.id, account_id=account.id,
                                           category_id=category.id if category else None, kind=kind,
                                           description=description, amount=amount, occurred_on=occurred_on,
                                           recurring=recurring)
                        st.success("Movimiento actualizado.")
                        st.rerun()
                    except FinanceError as error:
                        show_error(error)
                if st.button("Eliminar movimiento", key="delete_transaction", icon=":material/delete:"):
                    delete_transaction(session, chosen.id)
                    st.success("Movimiento eliminado.")
                    st.rerun()
        else:
            st.caption("No hay movimientos que coincidan con los filtros.")

    with tab_categories:
        with st.form("new_category"):
            name = st.text_input("Nombre de la categoría")
            kind_label = st.selectbox("Se aplica a", list(KINDS), key="category_kind")
            color = st.color_picker("Color", "#5B7C72")
            submitted = st.form_submit_button("Crear categoría")
        if submitted:
            try:
                create_category(session, name, KINDS[kind_label], color)
                st.success("Categoría creada.")
                st.rerun()
            except FinanceError as error:
                show_error(error)
        if categories:
            st.dataframe(pd.DataFrame([{"Categoría": item.name, "Tipo": "Ingreso" if item.kind == "income" else "Gasto"}
                                      for item in categories]), hide_index=True, width="stretch")

    with tab_recurring:
        st.caption("Las reglas generan como máximo un movimiento mensual cuando se procesan. No hay cargos bancarios automáticos.")
        if not accounts:
            st.info("Crea una cuenta para configurar reglas recurrentes.")
        else:
            rules = session.scalars(select(RecurringRule).order_by(RecurringRule.description)).all()
            kind_label = st.segmented_control("Tipo", list(KINDS), default="Gasto", key="recurring_kind")
            kind = KINDS[kind_label]
            eligible = [item for item in categories if item.kind == kind]
            with st.form("create_recurring_rule"):
                description = st.text_input("Descripción", placeholder="Alquiler")
                account = st.selectbox("Cuenta", accounts, format_func=lambda item: item.name, key="rule_account")
                category = st.selectbox("Categoría", eligible, format_func=lambda item: item.name,
                                        index=None, placeholder="Sin categoría", key="rule_category")
                amount = st.number_input(f"Importe ({settings.currency})", min_value=0.01, step=10.0, format="%.2f", key="rule_amount")
                day = st.number_input("Día del mes", min_value=1, max_value=31, value=1, step=1)
                starts_on = st.date_input("Vigente desde", value=date.today(), format="DD/MM/YYYY", key="rule_start")
                submitted = st.form_submit_button("Crear regla", type="primary")
            if submitted:
                try:
                    create_recurring_rule(session, account_id=account.id,
                                          category_id=category.id if category else None,
                                          kind=kind, description=description, amount=amount,
                                          day_of_month=int(day), starts_on=starts_on)
                    st.success("Regla mensual creada.")
                    st.rerun()
                except FinanceError as error:
                    show_error(error)
            if rules:
                if st.button("Procesar movimientos vencidos de este mes", icon=":material/event_repeat:"):
                    try:
                        count = process_recurring_rules(session, date.today())
                        st.success(f"Se generaron {count} movimiento(s).")
                        st.rerun()
                    except FinanceError as error:
                        show_error(error)
                for rule in rules:
                    label = f"{'Activa' if rule.active else 'Pausada'} · {rule.description} · día {rule.day_of_month} · {money(rule.amount, settings.currency)}"
                    column, action = st.columns([4, 1])
                    column.write(label)
                    if action.button("Pausar" if rule.active else "Reanudar", key=f"toggle_rule_{rule.id}"):
                        set_recurring_rule_active(session, rule.id, not rule.active)
                        st.rerun()
