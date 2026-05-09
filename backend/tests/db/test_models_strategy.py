"""Strategy + StrategyVersion 모델 테스트."""

from datetime import UTC, datetime

import pytest

from app.models.strategy import Strategy, StrategyVersion
from app.models.user import User


@pytest.fixture
def user(db_session):
    u = User(email="trader@example.com", display_name="홍길동")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def _sample_strategy_json() -> dict:
    return {
        "name": "거래량 돌파 스윙 전략",
        "version": "1.0",
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 20, "operator": ">"},
                {"type": "volume_ratio", "period": 20, "operator": ">=", "value": 2.0},
            ],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [
                {"type": "take_profit", "percent": 7.0, "trigger": "intraday_high"},
                {"type": "stop_loss", "percent": 3.0},
            ],
        },
    }


def test_create_strategy_with_user(db_session, user):
    s = Strategy(
        user_id=user.id,
        name="거래량 돌파",
        description="거래량 급증 종목 매수",
        strategy_json=_sample_strategy_json(),
        tags=["거래량", "스윙"],
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)

    assert s.id is not None
    assert s.user_id == user.id
    assert s.favorite is False
    assert s.deleted_at is None
    assert s.tags == ["거래량", "스윙"]
    # JSON 컬럼 round-trip
    assert s.strategy_json["entry"]["conditions"][0]["type"] == "price_vs_ma"


def test_strategy_user_relationship(db_session, user):
    s = Strategy(
        user_id=user.id,
        name="A",
        strategy_json={"entry": {"logic": "AND", "conditions": []}},
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    db_session.refresh(user)

    # 양방향
    assert s.user.id == user.id
    assert s in user.strategies


def test_create_strategy_version(db_session, user):
    s = Strategy(
        user_id=user.id,
        name="A",
        strategy_json={"entry": {"logic": "AND", "conditions": []}},
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)

    v1 = StrategyVersion(
        strategy_id=s.id,
        version=1,
        strategy_json=s.strategy_json,
        change_note="첫 버전",
        created_at=datetime.now(UTC),
    )
    v2 = StrategyVersion(
        strategy_id=s.id,
        version=2,
        strategy_json=_sample_strategy_json(),
        change_note="익절/손절 조건 추가",
        created_at=datetime.now(UTC),
    )
    db_session.add_all([v1, v2])
    db_session.commit()
    db_session.refresh(s)

    assert len(s.versions) == 2
    # order_by="version" → 1, 2 순서
    assert [v.version for v in s.versions] == [1, 2]
    assert s.versions[1].change_note == "익절/손절 조건 추가"


def test_strategy_versions_cascade_delete(db_session, user):
    s = Strategy(
        user_id=user.id,
        name="A",
        strategy_json={"entry": {"logic": "AND", "conditions": []}},
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)

    v = StrategyVersion(
        strategy_id=s.id,
        version=1,
        strategy_json={"entry": {"logic": "AND", "conditions": []}},
        created_at=datetime.now(UTC),
    )
    db_session.add(v)
    db_session.commit()

    s_id = s.id
    db_session.delete(s)
    db_session.commit()

    # cascade='all, delete-orphan' → version도 삭제
    remaining = db_session.query(StrategyVersion).filter_by(strategy_id=s_id).all()
    assert remaining == []


def test_strategy_soft_delete_via_deleted_at(db_session, user):
    """deleted_at만 채워두는 soft delete 패턴.

    물리 삭제하지 않고 쿼리 시 deleted_at IS NULL로 필터링.
    이 step에서는 컬럼만 검증; 헬퍼 메서드는 후속 step.
    """
    s = Strategy(
        user_id=user.id,
        name="A",
        strategy_json={"entry": {"logic": "AND", "conditions": []}},
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)

    s.deleted_at = datetime.now(UTC)
    db_session.commit()
    db_session.refresh(s)

    assert s.deleted_at is not None
    # 행은 여전히 존재
    found = db_session.query(Strategy).filter_by(id=s.id).first()
    assert found is not None


def test_user_cascade_deletes_strategies(db_session):
    """User 삭제 시 strategies cascade. (관련 백테스트가 없을 때만 권장)"""
    u = User(email="cascade@example.com")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)

    s = Strategy(
        user_id=u.id,
        name="A",
        strategy_json={"entry": {"logic": "AND", "conditions": []}},
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)

    s_id = s.id
    db_session.delete(u)
    db_session.commit()

    assert db_session.query(Strategy).filter_by(id=s_id).first() is None


def test_strategy_repr(db_session, user):
    s = Strategy(
        user_id=user.id,
        name="이동평균 골든크로스",
        strategy_json={"entry": {"logic": "AND", "conditions": []}},
    )
    db_session.add(s)
    db_session.commit()
    assert "이동평균 골든크로스" in repr(s)
