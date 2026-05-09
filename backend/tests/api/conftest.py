"""API 테스트 공통 fixture.

각 테스트가 독립된 file-based SQLite를 사용 (in-memory는 connection별 독립이라
dependency가 새 session을 만들 때 테이블이 안 보임).
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.db.session import create_db_engine, init_db, make_session_factory
from app.main import app
from app.main_state import reset_engine_for_tests
from app.models.user import User


@pytest.fixture
def db_engine():
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "test.db")
    url = f"sqlite:///{path}"
    engine = create_db_engine(url)
    init_db(engine)

    SessionLocal = make_session_factory(engine)
    with SessionLocal() as session:
        if session.get(User, 1) is None:
            session.add(User(id=1, email="system@local"))
            session.commit()

    reset_engine_for_tests(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        try:
            if os.path.exists(path):
                os.unlink(path)
            os.rmdir(tmpdir)
        except OSError:
            pass


@pytest.fixture
def client(db_engine):  # noqa: ARG001
    return TestClient(app)
