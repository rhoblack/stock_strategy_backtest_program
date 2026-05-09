"""strategy_service 테스트."""

import pytest

from app.core.exceptions import StrategyNotFoundError
from app.models.strategy import StrategyVersion
from app.services import strategy_service


def test_create_strategy_creates_first_version(db_session, user, sample_strategy_json):
    s = strategy_service.create_strategy(
        db_session,
        user_id=user.id,
        name="거래량 돌파",
        strategy_json=sample_strategy_json,
        tags=["거래량", "돌파"],
    )
    assert s.id is not None
    assert s.tags == ["거래량", "돌파"]

    versions = db_session.query(StrategyVersion).filter_by(strategy_id=s.id).all()
    assert len(versions) == 1
    assert versions[0].version == 1
    assert versions[0].change_note == "초기 버전"


def test_update_strategy_json_creates_new_version(db_session, user, sample_strategy_json):
    s = strategy_service.create_strategy(
        db_session, user_id=user.id, name="A", strategy_json=sample_strategy_json
    )

    new_json = dict(sample_strategy_json)
    new_json["entry"] = {
        "logic": "AND",
        "conditions": [{"type": "price_vs_ma", "ma_period": 20, "operator": ">"}],
    }

    updated = strategy_service.update_strategy(
        db_session, s.id, strategy_json=new_json, change_note="ma_period 5→20"
    )
    assert updated.strategy_json["entry"]["conditions"][0]["ma_period"] == 20

    versions = strategy_service.list_strategy_versions(db_session, s.id)
    assert len(versions) == 2
    assert versions[1].version == 2
    assert versions[1].change_note == "ma_period 5→20"


def test_update_metadata_only_does_not_create_new_version(
    db_session, user, sample_strategy_json
):
    s = strategy_service.create_strategy(
        db_session, user_id=user.id, name="A", strategy_json=sample_strategy_json
    )
    strategy_service.update_strategy(db_session, s.id, name="A2", favorite=True)

    versions = strategy_service.list_strategy_versions(db_session, s.id)
    assert len(versions) == 1  # JSON 안 바뀜


def test_duplicate_strategy(db_session, user, sample_strategy_json):
    s = strategy_service.create_strategy(
        db_session, user_id=user.id, name="원본", strategy_json=sample_strategy_json,
        tags=["거래량"], favorite=True,
    )

    dup = strategy_service.duplicate_strategy(db_session, s.id, new_name="복사본")
    assert dup.id != s.id
    assert dup.name == "복사본"
    assert dup.user_id == user.id
    assert dup.tags == ["거래량"]
    assert dup.favorite is False  # 복사본은 즐겨찾기 해제

    # 깊은 복사 — 원본 strategy_json 변경 시 dup 영향 없음
    s.strategy_json["entry"]["conditions"][0]["ma_period"] = 999
    db_session.commit()
    db_session.refresh(dup)
    assert dup.strategy_json["entry"]["conditions"][0]["ma_period"] == 5


def test_soft_delete(db_session, user, sample_strategy_json):
    s = strategy_service.create_strategy(
        db_session, user_id=user.id, name="A", strategy_json=sample_strategy_json
    )
    strategy_service.soft_delete_strategy(db_session, s.id)

    # 기본 list/get은 안 보임
    assert strategy_service.list_strategies(db_session, user_id=user.id) == []
    with pytest.raises(StrategyNotFoundError):
        strategy_service.get_strategy(db_session, s.id)

    # include_deleted/allow_deleted 옵션은 보임
    assert len(strategy_service.list_strategies(db_session, user_id=user.id, include_deleted=True)) == 1
    s2 = strategy_service.get_strategy(db_session, s.id, allow_deleted=True)
    assert s2.deleted_at is not None


def test_list_strategies_orders_by_updated_at_desc(db_session, user, sample_strategy_json):
    s1 = strategy_service.create_strategy(
        db_session, user_id=user.id, name="A", strategy_json=sample_strategy_json
    )
    s2 = strategy_service.create_strategy(
        db_session, user_id=user.id, name="B", strategy_json=sample_strategy_json
    )

    # B 수정 → updated_at 갱신
    strategy_service.update_strategy(db_session, s1.id, name="A1")

    listed = strategy_service.list_strategies(db_session, user_id=user.id)
    # s1이 최근 수정 → 첫번째
    assert listed[0].id == s1.id
    assert listed[1].id == s2.id


def test_get_strategy_not_found(db_session):
    with pytest.raises(StrategyNotFoundError):
        strategy_service.get_strategy(db_session, 999)


def test_list_strategy_versions_orders_ascending(db_session, user, sample_strategy_json):
    s = strategy_service.create_strategy(
        db_session, user_id=user.id, name="A", strategy_json=sample_strategy_json
    )
    new_json = dict(sample_strategy_json)
    new_json["filters"] = {"logic": "AND", "conditions": []}
    strategy_service.update_strategy(db_session, s.id, strategy_json=new_json)

    versions = strategy_service.list_strategy_versions(db_session, s.id)
    assert [v.version for v in versions] == [1, 2]
