"""앱 시작 시 1회 초기화되는 글로벌 상태 (DB engine).

운영 시에는 alembic으로 schema 관리. dev/test는 init_db로 자동 생성.
"""

from __future__ import annotations

import os
from threading import Lock
from typing import Optional

from sqlalchemy import Engine

from app.db.session import create_db_engine, init_db
from app.models.user import User

_lock = Lock()
_engine: Optional[Engine] = None  # noqa: UP045


def get_engine() -> Engine:
    global _engine
    with _lock:
        if _engine is None:
            url = os.getenv("APP_DATABASE_URL", "sqlite:///dev.db")
            _engine = create_db_engine(url)
            init_db(_engine)
            _ensure_system_user(_engine)
        return _engine


def _ensure_system_user(engine: Engine) -> None:
    """user_id=1 시스템 유저 보장 (FK 무결성)."""
    from app.db.session import make_session_factory

    SessionLocal = make_session_factory(engine)
    with SessionLocal() as session:
        user = session.get(User, 1)
        if user is None:
            session.add(User(id=1, email="system@local"))
            session.commit()


def reset_engine_for_tests(engine: Engine) -> None:
    """테스트에서 in-memory engine을 강제 주입."""
    global _engine
    with _lock:
        _engine = engine
