"""data_pipeline jobs 테스트 공통 fixture (Phase 11 step 028).

각 테스트가 독립된 in-memory SQLite + 빈 스키마로 시작.
외부 fetch는 일절 없으며 모든 데이터는 합성 fixture만 사용.
"""

from __future__ import annotations

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


@pytest.fixture
def session_factory(db_engine):
    """잡이 호출할 때마다 새 세션을 반환하는 callable.

    잡은 _session_scope에서 세션을 close()하므로 fixture가 매번 새 세션을 만들어야 한다.
    """
    SessionLocal = make_session_factory(db_engine)
    return lambda: SessionLocal()
