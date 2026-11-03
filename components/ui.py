from __future__ import annotations

from datetime import date
from decimal import Decimal

import streamlit as st

MONTHS_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre")
WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root { --ink:#23332d; --muted:#718078; --paper:#f6f7f3; --line:#e1e6df; --accent:#3f765e; }
        .stApp { background:var(--paper); color:var(--ink); }
        [data-testid="stSidebar"] { background:#edf1ea; border-right:1px solid var(--line); }
        [data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:8px; padding:16px 18px; }
        [data-testid="stMetricLabel"] { color:var(--muted); }
        h1,h2,h3 { color:var(--ink); letter-spacing:0 !important; }
        .block-container { max-width:1420px; padding-top:2rem; padding-bottom:3rem; }
        div[data-testid="stForm"] { background:#fff; border:1px solid var(--line); border-radius:8px; padding:18px; }
        div[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:8px; }
        button[kind="primary"] { background:var(--accent); border-color:var(--accent); }
        @media (max-width: 700px) { .block-container { padding:1rem 1rem 2rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def money(value: Decimal | float | int, currency: str = "EUR") -> str:
    symbol = {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency, currency)
    rendered = f"{Decimal(str(value)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{rendered} {symbol}"


def format_date_es(value: date, include_weekday: bool = False) -> str:
    rendered = f"{value.day:02d} de {MONTHS_ES[value.month - 1]} de {value.year}"
    return f"{WEEKDAYS_ES[value.weekday()]}, {rendered}" if include_weekday else rendered


def show_error(error: Exception) -> None:
    st.error(str(error))


def date_input(label: str, key: str, value: date | None = None):
    return st.date_input(label, value=value or date.today(), format="DD/MM/YYYY", key=key)
