from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from database.db import make_engine, initialize_database, make_session_factory
from models.base import Base


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine("sqlite:///:memory:")
    initialize_database(engine)
    factory = make_session_factory(engine)
    with factory() as database_session:
        yield database_session
    Base.metadata.drop_all(engine)
    engine.dispose()
