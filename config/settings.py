from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "Finanzas"
    currency: str = os.getenv("FINANZAS_CURRENCY", "EUR")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/finanzas.db")

    @property
    def currency_symbol(self) -> str:
        return {"EUR": "€", "USD": "$", "GBP": "£"}.get(self.currency, self.currency)


settings = Settings()


def ensure_data_directory(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix) and database_url != "sqlite:///:memory:":
        path = Path(database_url[len(prefix):])
        if not path.is_absolute():
            path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)
