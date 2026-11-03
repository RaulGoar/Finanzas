from __future__ import annotations

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from config.settings import ensure_data_directory, settings
from models.base import Base


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or settings.database_url
    ensure_data_directory(url)
    options = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=options, future=True)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def initialize_database(engine: Engine) -> None:
    import models.entities  # noqa: F401

    if engine.dialect.name == "sqlite":
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        preparer = engine.dialect.identifier_preparer
        with engine.begin() as connection:
            for table in Base.metadata.sorted_tables:
                if table.name not in existing_tables:
                    continue
                existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name in existing_columns:
                        continue
                    if not column.nullable and column.server_default is None and column.default is None:
                        raise RuntimeError(f"No se puede migrar automáticamente la columna {table.name}.{column.name}.")
                    definition = f"ALTER TABLE {preparer.quote(table.name)} ADD COLUMN {preparer.quote(column.name)} {column.type.compile(engine.dialect)}"
                    if column.server_default is not None:
                        definition += f" DEFAULT {column.server_default.arg}"
                    connection.execute(text(definition))
    Base.metadata.create_all(engine)
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_deduplication_key "
                "ON transactions (deduplication_key)"
            ))


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


engine = make_engine()
SessionLocal = make_session_factory(engine)
