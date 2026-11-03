from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from components.ui import money, show_error
from config.settings import settings
from models.entities import Account, Asset, Investment, InvestmentTrade, Liability
from services.finance import (ASSET_TYPES, INVESTMENT_TYPES, LIABILITY_TYPES, FinanceError,
                              create_asset, create_investment, create_liability, delete_asset,
                              delete_liability, investment_holdings, record_trade,
                              update_asset, update_investment_price, update_liability)


def render(session: Session) -> None:
    st.title("Patrimonio e inversiones")
    assets_tab, debts_tab, investments_tab = st.tabs(["Activos", "Deudas", "Inversiones"])

    with assets_tab:
        assets = session.scalars(select(Asset).order_by(Asset.name)).all()
        with st.expander("Añadir activo", expanded=not assets):
            with st.form("add_asset"):
                name = st.text_input("Nombre", placeholder="Vivienda principal")
                asset_type = st.selectbox("Tipo", sorted(ASSET_TYPES))
                value = st.number_input(f"Valor actual ({settings.currency})", min_value=0.0, step=1000.0, format="%.2f")
                valued_on = st.date_input("Valoración a fecha de", value=date.today(), format="DD/MM/YYYY")
                notes = st.text_input("Notas (opcional)")
                submitted = st.form_submit_button("Guardar activo", type="primary")
            if submitted:
                try:
                    create_asset(session, name, asset_type, value, valued_on, notes)
                    st.success("Activo registrado.")
                    st.rerun()
                except FinanceError as error:
                    show_error(error)
        if assets:
            st.dataframe(pd.DataFrame([{"Activo": item.name, "Tipo": item.asset_type,
                                       "Valor": money(item.value, settings.currency),
                                       "Valorado": item.valued_on.strftime("%d/%m/%Y")} for item in assets]),
                         hide_index=True, width="stretch")
            with st.expander("Editar o eliminar activo"):
                selected_asset = st.selectbox("Activo", assets, format_func=lambda item: item.name, key="edit_asset_select")
                with st.form("edit_asset"):
                    edited_name = st.text_input("Nombre", value=selected_asset.name, key="edit_asset_name")
                    edited_type = st.selectbox("Tipo", sorted(ASSET_TYPES), index=sorted(ASSET_TYPES).index(selected_asset.asset_type), key="edit_asset_type")
                    edited_value = st.number_input(f"Valor actual ({settings.currency})", min_value=0.0, value=float(selected_asset.value), step=1000.0, format="%.2f", key="edit_asset_value")
                    edited_date = st.date_input("Valoración a fecha de", value=selected_asset.valued_on, format="DD/MM/YYYY", key="edit_asset_date")
                    edited_notes = st.text_input("Notas", value=selected_asset.notes or "", key="edit_asset_notes")
                    save_asset = st.form_submit_button("Guardar cambios", type="primary")
                if save_asset:
                    try:
                        update_asset(session, selected_asset.id, edited_name, edited_type, edited_value, edited_date, edited_notes)
                        st.success("Activo actualizado.")
                        st.rerun()
                    except FinanceError as error:
                        show_error(error)
                confirm_asset = st.checkbox("Confirmo eliminar este activo", key="confirm_asset_delete")
                if st.button("Eliminar activo", disabled=not confirm_asset, key="delete_asset"):
                    delete_asset(session, selected_asset.id)
                    st.rerun()
        else:
            st.caption("Registra inmuebles, vehículos u otros bienes para incluirlos en tu patrimonio neto.")

    with debts_tab:
        liabilities = session.scalars(select(Liability).order_by(Liability.name)).all()
        with st.expander("Añadir deuda", expanded=not liabilities):
            with st.form("add_liability"):
                name = st.text_input("Nombre", placeholder="Hipoteca")
                liability_type = st.selectbox("Tipo", sorted(LIABILITY_TYPES))
                balance = st.number_input(f"Saldo pendiente ({settings.currency})", min_value=0.0, step=1000.0, format="%.2f")
                due_on = st.date_input("Fecha de vencimiento (opcional)", value=date.today(), format="DD/MM/YYYY")
                notes = st.text_input("Notas (opcional)", key="liability_notes")
                submitted = st.form_submit_button("Guardar deuda", type="primary")
            if submitted:
                try:
                    create_liability(session, name, liability_type, balance, due_on, notes)
                    st.success("Deuda registrada.")
                    st.rerun()
                except FinanceError as error:
                    show_error(error)
        if liabilities:
            st.dataframe(pd.DataFrame([{"Deuda": item.name, "Tipo": item.liability_type,
                                       "Pendiente": money(item.balance, settings.currency),
                                       "Vencimiento": item.due_on.strftime("%d/%m/%Y") if item.due_on else "—"}
                                      for item in liabilities]), hide_index=True, width="stretch")
            with st.expander("Editar o eliminar deuda"):
                selected_liability = st.selectbox("Deuda", liabilities, format_func=lambda item: item.name, key="edit_liability_select")
                with st.form("edit_liability"):
                    edited_name = st.text_input("Nombre", value=selected_liability.name, key="edit_liability_name")
                    edited_type = st.selectbox("Tipo", sorted(LIABILITY_TYPES), index=sorted(LIABILITY_TYPES).index(selected_liability.liability_type), key="edit_liability_type")
                    edited_balance = st.number_input(f"Saldo pendiente ({settings.currency})", min_value=0.0, value=float(selected_liability.balance), step=1000.0, format="%.2f", key="edit_liability_balance")
                    has_due_date = st.checkbox("Tiene fecha de vencimiento", value=selected_liability.due_on is not None, key="edit_liability_has_due")
                    edited_due = st.date_input("Fecha de vencimiento", value=selected_liability.due_on or date.today(), format="DD/MM/YYYY", key="edit_liability_due")
                    edited_notes = st.text_input("Notas", value=selected_liability.notes or "", key="edit_liability_notes")
                    save_liability = st.form_submit_button("Guardar cambios", type="primary")
                if save_liability:
                    try:
                        update_liability(session, selected_liability.id, edited_name, edited_type,
                                         edited_balance, edited_due if has_due_date else None, edited_notes)
                        st.success("Deuda actualizada.")
                        st.rerun()
                    except FinanceError as error:
                        show_error(error)
                confirm_liability = st.checkbox("Confirmo eliminar esta deuda", key="confirm_liability_delete")
                if st.button("Eliminar deuda", disabled=not confirm_liability, key="delete_liability"):
                    delete_liability(session, selected_liability.id)
                    st.rerun()
        else:
            st.caption("Registra préstamos, hipotecas u otras deudas.")

    with investments_tab:
        accounts = session.scalars(select(Account).where(Account.active.is_(True)).order_by(Account.name)).all()
        investments = session.scalars(select(Investment).order_by(Investment.name)).all()
        add_tab, trade_tab, positions_tab = st.tabs(["Añadir activo", "Registrar operación", "Cartera"])
        with add_tab:
            with st.form("add_investment"):
                name = st.text_input("Nombre del activo", placeholder="Fondo indexado mundial")
                ticker = st.text_input("Símbolo (opcional)")
                asset_type = st.selectbox("Tipo de inversión", sorted(INVESTMENT_TYPES))
                st.text_input("Moneda", value=settings.currency, disabled=True)
                submitted = st.form_submit_button("Añadir a cartera", type="primary")
            if submitted:
                try:
                    create_investment(session, name, asset_type, ticker, settings.currency)
                    st.success("Activo añadido. No se consultan cotizaciones externas.")
                    st.rerun()
                except FinanceError as error:
                    show_error(error)
        with trade_tab:
            if not investments or not accounts:
                st.info("Añade una inversión y una cuenta antes de registrar operaciones.")
            else:
                with st.form("investment_trade"):
                    investment = st.selectbox("Activo", investments, format_func=lambda item: f"{item.name} ({item.ticker})" if item.ticker else item.name)
                    side_label = st.radio("Operación", ["Compra", "Venta"], horizontal=True)
                    account = st.selectbox("Cuenta de efectivo", accounts, format_func=lambda item: item.name)
                    units = st.number_input("Unidades", min_value=0.00000001, step=1.0, format="%.8f")
                    unit_price = st.number_input(f"Precio por unidad ({investment.currency})", min_value=0.000001, step=1.0, format="%.6f")
                    commission = st.number_input(f"Comisión ({investment.currency})", min_value=0.0, step=1.0, format="%.2f")
                    traded_on = st.date_input("Fecha de operación", value=date.today(), format="DD/MM/YYYY")
                    submitted = st.form_submit_button("Registrar operación", type="primary")
                if submitted:
                    try:
                        record_trade(session, investment.id, account.id, "buy" if side_label == "Compra" else "sell",
                                     units, unit_price, commission, traded_on)
                        st.success("Operación registrada; el efectivo se ha reflejado en la cuenta.")
                        st.rerun()
                    except FinanceError as error:
                        show_error(error)
        with positions_tab:
            rows = []
            for item in investments:
                units, cost, realized = investment_holdings(session, item.id)
                market_value = units * Decimal(item.current_price) if item.current_price is not None else Decimal("0")
                rows.append({"Activo": item.name, "Tipo": item.asset_type, "Unidades": f"{units:.8f}",
                             "Precio manual": money(item.current_price, item.currency) if item.current_price is not None else "Sin precio",
                             "Coste restante": money(cost, item.currency), "Valor estimado": money(market_value, item.currency),
                             "No realizado": money(market_value - cost, item.currency), "Realizado": money(realized, item.currency)})
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
                st.caption("Las valoraciones usan precios introducidos por ti y la moneda base configurada; no hay cotizaciones ni conversión de divisas automáticas.")
                with st.expander("Actualizar precio de mercado manual"):
                    with st.form("manual_investment_price"):
                        selected_investment = st.selectbox("Activo", investments, format_func=lambda item: item.name, key="manual_price_investment")
                        current_price = st.number_input(f"Precio actual por unidad ({settings.currency})", min_value=0.000001,
                                                         value=float(selected_investment.current_price or 0.000001),
                                                         step=1.0, format="%.6f")
                        update_price = st.form_submit_button("Guardar precio indicado", type="primary")
                    if update_price:
                        try:
                            update_investment_price(session, selected_investment.id, current_price)
                            st.success("Precio manual actualizado.")
                            st.rerun()
                        except FinanceError as error:
                            show_error(error)
            else:
                st.caption("Tu cartera aparecerá aquí cuando añadas inversiones.")
