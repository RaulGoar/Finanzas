from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from database.db import engine


def create_backup() -> bytes:
    if engine.dialect.name != "sqlite":
        raise RuntimeError("La copia descargable está disponible actualmente para SQLite.")
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as temporary:
        backup_path = Path(temporary.name)
    source = engine.raw_connection()
    destination = sqlite3.connect(backup_path)
    try:
        source.driver_connection.backup(destination)
        destination.close()
        return backup_path.read_bytes()
    finally:
        source.close()
        if destination:
            try:
                destination.close()
            except sqlite3.Error:
                pass
        backup_path.unlink(missing_ok=True)
