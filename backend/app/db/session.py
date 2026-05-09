"""DB 엔진/세션 헬퍼.

MVP는 SQLite. PostgreSQL로 전환 시 url만 교체.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base


def create_db_engine(url: str, *, echo: bool = False) -> Engine:
    """DB 엔진 생성. SQLite는 같은 connection을 thread 간 공유 가능하도록 옵션 추가.

    예시:
        create_db_engine("sqlite:///dev.db")
        create_db_engine("sqlite:///:memory:")
        create_db_engine("postgresql://user:pwd@localhost/dbname")
    """
    if url.startswith("sqlite"):
        return create_engine(
            url,
            echo=echo,
            connect_args={"check_same_thread": False},
            future=True,
        )
    return create_engine(url, echo=echo, future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """모든 등록된 모델로 테이블 생성. Alembic 도입 전 임시.

    `app.models`를 import한 뒤 호출해야 모델이 Base.metadata에 등록되어 있음.
    """
    # 모델 등록 트리거
    import app.models  # noqa: F401

    Base.metadata.create_all(engine)


def drop_db(engine: Engine) -> None:
    """모든 테이블 제거. 테스트 정리용."""
    import app.models  # noqa: F401

    Base.metadata.drop_all(engine)
