"""services 테스트 공통 fixture.

DB fixture를 tests/db/conftest.py에서 가져온다.
"""

import pytest
from sqlalchemy.orm import Session

from app.db.session import create_db_engine, drop_db, init_db, make_session_factory
from app.models.user import User


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
def user(db_session) -> User:
    u = User(email="trader@example.com", display_name="홍길동")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def sample_strategy_json() -> dict:
    return {
        "name": "거래량 돌파",
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 5, "operator": ">"},
            ],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [
                {"type": "take_profit", "percent": 5.0, "trigger": "intraday_high"},
                {"type": "stop_loss", "percent": 3.0},
            ],
        },
    }
