"""DB 테스트 공통 fixture.

각 테스트가 독립된 in-memory SQLite + 빈 스키마로 시작.
"""

import pytest
from sqlalchemy.orm import Session

from app.db.session import create_db_engine, drop_db, init_db, make_session_factory


@pytest.fixture
def db_engine():
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    try:
        yield engine
    finally:
        drop_db(engine)
        engine.dispose()


@pytest.fixture
def db_session(db_engine):
    SessionLocal = make_session_factory(db_engine)
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
