from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from components.ui import money, show_error
from config.settings import settings
from models.entities import Account, Transaction
from services.finance import FinanceError, account_balances, create_account, transfer


def render(session: Session) -> None:
    st.title("Cuentas")
    accounts = session.scalars(select(Account).where(Account.active.is_(True)).order_by(Account.name)).all()
    balances = account_balances(session)
    tab_accounts, tab_transfer, tab_activity = st.tabs(["Mis cuentas", "Transferir", "Movimientos"])

    with tab_accounts:
        with st.expander("Añadir cuenta", expanded=not accounts):
            with st.form("create_account"):
                name = st.text_input("Nombre", placeholder="Cuenta principal")
                account_type = st.selectbox("Tipo", ["Corriente", "Ahorro", "Efectivo"])
                institution = st.text_input("Entidad (opcional)")
                opening = st.number_input(f"Saldo inicial ({settings.currency})", min_value=0.0, step=50.0, format="%.2f")
                submitted = st.form_submit_button("Crear cuenta", type="primary")
            if submitted:
                try:
                    create_account(session, name, account_type, opening, institution)
                    st.success("Cuenta creada.")
                    st.rerun()
                except FinanceError as error:
                    show_error(error)
        if accounts:
            st.dataframe(pd.DataFrame([{"Cuenta": item.name, "Tipo": item.account_type,
                                       "Entidad": item.institution or "—",
                                       "Saldo": money(balances.get(item.id, Decimal("0")), settings.currency)}
                                      for item in accounts]), hide_index=True, width="stretch")
        else:
            st.info("Todavía no tienes cuentas. Crea una para registrar ingresos y gastos.")

    with tab_transfer:
        if len(accounts) < 2:
            st.info("Necesitas al menos dos cuentas activas para hacer una transferencia.")
        else:
            account_options = {f"{item.name} · {money(balances[item.id], settings.currency)}": item.id for item in accounts}
            labels = list(account_options)
            with st.form("transfer_form"):
                source_label = st.selectbox("Desde", labels, key="transfer_source")
                destination_label = st.selectbox("Hacia", labels, index=1, key="transfer_destination")
                amount = st.number_input(f"Importe ({settings.currency})", min_value=0.01, step=10.0, format="%.2f")
                occurred_on = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY", key="transfer_date")
                description = st.text_input("Descripción", value="Transferencia entre cuentas")
                submitted = st.form_submit_button("Transferir", type="primary")
            if submitted:
                try:
                    transfer(session, account_options[source_label], account_options[destination_label], amount, occurred_on, description)
                    st.success("Transferencia registrada en ambas cuentas.")
                    st.rerun()
                except FinanceError as error:
                    show_error(error)

    with tab_activity:
        if not accounts:
            st.info("Crea una cuenta para consultar sus movimientos.")
        else:
            selected = st.selectbox("Cuenta", accounts, format_func=lambda item: item.name, key="activity_account")
            rows = session.scalars(select(Transaction).where(Transaction.account_id == selected.id)
                                   .order_by(Transaction.occurred_on.desc(), Transaction.id.desc())).all()
            if rows:
                data = []
                for row in rows:
                    signed = row.amount if row.kind in {"income", "transfer_in"} else -row.amount
                    data.append({"Fecha": row.occurred_on.strftime("%d/%m/%Y"), "Descripción": row.description,
                                 "Tipo": {"income": "Ingreso", "expense": "Gasto", "transfer_in": "Transferencia recibida",
                                          "transfer_out": "Transferencia enviada"}.get(row.kind, row.kind),
                                 "Importe": money(signed, settings.currency)})
                st.dataframe(pd.DataFrame(data), hide_index=True, width="stretch")
            else:
                st.caption("Esta cuenta todavía no tiene movimientos.")
