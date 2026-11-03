from __future__ import annotations

import streamlit as st

from components.ui import apply_theme
from config.settings import settings
from database.db import SessionLocal, initialize_database, engine
from pages import accounts, balance_sheet, dashboard, movements, planning, reports
from services.finance import seed_categories

st.set_page_config(page_title="Finanzas", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
apply_theme()
initialize_database(engine)

PAGES = {
    "Resumen": ("⌂", dashboard.render),
    "Cuentas": ("▤", accounts.render),
    "Movimientos": ("↕", movements.render),
    "Planificación": ("◎", planning.render),
    "Patrimonio e inversiones": ("◈", balance_sheet.render),
    "Informes": ("▥", reports.render),
}

with st.sidebar:
    st.markdown("# Finanzas")
    st.caption("Tu panorama financiero, en un solo lugar.")
    page = st.radio("Navegación", list(PAGES), label_visibility="collapsed")
    st.divider()
    st.caption(f"Moneda: **{settings.currency}**")
    st.caption("Los datos se guardan en una base SQLite local. No se conectan bancos ni servicios de cotización.")
    st.divider()
    from database.backup import create_backup

    st.download_button("Descargar copia de seguridad", create_backup(), "finanzas-backup.sqlite",
                       "application/vnd.sqlite3", icon=":material/backup:", width="stretch")

session = SessionLocal()
try:
    seed_categories(session)
    icon, render_page = PAGES[page]
    render_page(session)
except Exception as error:
    st.error("No se pudo completar la operación. Tus cambios no guardados no se han aplicado.")
    st.exception(error)
finally:
    session.close()
