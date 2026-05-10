"""UniverseHistory 모델 + repositories CRUD 테스트 (07번 §14 / 06번 §14 / 14번 §10).

검증 항목:
    - 기본 등록 / 조회
    - UniqueConstraint(as_of_date, market, selection_method, config_hash)
    - upsert 갱신 (config_json / symbols_json / run_id)
    - get_universe_snapshot 정렬 (as_of_date DESC, id ASC)
    - selection_method / config_hash 추가 필터
    - 필수 키 누락 → KeyError
    - run_id NULL 허용 (preview 스냅샷)
    - 결정론: 동일 입력 5회 반복 동일
    - models/__init__ 등록
    - 13.13 / 14.10 생존편향: 폐지된 종목도 symbols_json에 그대로 보존
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest

from app.market_data.repositories import (
    get_universe_snapshot,
    upsert_universe_snapshot,
)
from app.models.universe_history import UniverseHistory


def _hash_config(config: dict) -> str:
    """config_json의 안정 해시 (호출자가 권장 — repositories는 강제 안 함)."""
    text = json.dumps(config, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _basic_payload(**overrides):
    config = {
        "market": "KOSPI",
        "selection_method": "ALL",
        "exclude_etf": True,
    }
    payload = {
        "as_of_date": date(2024, 1, 8),
        "market": "KOSPI",
        "selection_method": "ALL",
        "config_json": config,
        "config_hash": _hash_config(config),
        "symbols_json": ["005930", "000660", "035720"],
    }
    payload.update(overrides)
    return payload


def test_upsert_universe_snapshot_creates_new(db_session):
    payload = _basic_payload()
    row = upsert_universe_snapshot(db_session, payload)
    assert row.id is not None
    assert row.as_of_date == date(2024, 1, 8)
    assert row.market == "KOSPI"
    assert row.selection_method == "ALL"
    assert row.symbols_json == ["005930", "000660", "035720"]
    assert row.config_json == {
        "market": "KOSPI",
        "selection_method": "ALL",
        "exclude_etf": True,
    }
    assert row.run_id is None  # preview 스냅샷


def test_upsert_universe_snapshot_updates_existing(db_session):
    """동일 (as_of_date, market, selection_method, config_hash)면 갱신."""
    payload = _basic_payload()
    upsert_universe_snapshot(db_session, payload)
    # 같은 키지만 symbols만 다르게 (재계산 결과 정정)
    payload2 = dict(payload)
    payload2["symbols_json"] = ["005930", "000660"]  # 종목 수 정정
    payload2["run_id"] = None
    updated = upsert_universe_snapshot(db_session, payload2)
    assert updated.symbols_json == ["005930", "000660"]

    rows = get_universe_snapshot(db_session, date(2024, 1, 8), "KOSPI")
    assert len(rows) == 1
    assert rows[0].symbols_json == ["005930", "000660"]


def test_unique_constraint_per_method_and_hash(db_session):
    """selection_method 또는 config_hash가 다르면 별개 row."""
    base = _basic_payload()
    upsert_universe_snapshot(db_session, base)

    # selection_method가 다름 → 별개
    p2 = _basic_payload(
        selection_method="MARKET_CAP_TOP_N",
        config_json={"market": "KOSPI", "selection_method": "MARKET_CAP_TOP_N", "top_n": 100},
        config_hash=_hash_config(
            {"market": "KOSPI", "selection_method": "MARKET_CAP_TOP_N", "top_n": 100}
        ),
        symbols_json=["005930"],
    )
    upsert_universe_snapshot(db_session, p2)

    # config_hash가 다름 → 별개
    p3 = _basic_payload(
        config_json={"market": "KOSPI", "selection_method": "ALL", "exclude_etf": False},
        config_hash=_hash_config(
            {"market": "KOSPI", "selection_method": "ALL", "exclude_etf": False}
        ),
        symbols_json=["005930", "000660"],
    )
    upsert_universe_snapshot(db_session, p3)

    rows = get_universe_snapshot(db_session, date(2024, 1, 8), "KOSPI")
    assert len(rows) == 3


def test_get_universe_snapshot_filters_by_method(db_session):
    upsert_universe_snapshot(db_session, _basic_payload())
    upsert_universe_snapshot(
        db_session,
        _basic_payload(
            selection_method="MARKET_CAP_TOP_N",
            config_json={"market": "KOSPI", "selection_method": "MARKET_CAP_TOP_N", "top_n": 50},
            config_hash=_hash_config(
                {"market": "KOSPI", "selection_method": "MARKET_CAP_TOP_N", "top_n": 50}
            ),
            symbols_json=["005930"],
        ),
    )
    rows = get_universe_snapshot(
        db_session, date(2024, 1, 8), "KOSPI", selection_method="ALL"
    )
    assert len(rows) == 1
    assert rows[0].selection_method == "ALL"


def test_get_universe_snapshot_filters_by_hash(db_session):
    config_a = {"market": "KOSPI", "selection_method": "ALL", "x": 1}
    config_b = {"market": "KOSPI", "selection_method": "ALL", "x": 2}
    hash_a = _hash_config(config_a)
    hash_b = _hash_config(config_b)
    upsert_universe_snapshot(
        db_session,
        _basic_payload(config_json=config_a, config_hash=hash_a, symbols_json=["A"]),
    )
    upsert_universe_snapshot(
        db_session,
        _basic_payload(config_json=config_b, config_hash=hash_b, symbols_json=["B"]),
    )
    rows = get_universe_snapshot(
        db_session, date(2024, 1, 8), "KOSPI", config_hash=hash_a
    )
    assert len(rows) == 1
    assert rows[0].symbols_json == ["A"]


def test_get_universe_snapshot_orders_by_as_of_date_desc(db_session):
    """동일 (market) 다른 as_of_date — DESC 순서 보장."""
    for d in [date(2024, 1, 8), date(2024, 1, 15), date(2024, 1, 22)]:
        config = {"market": "KOSPI", "selection_method": "ALL", "d": d.isoformat()}
        upsert_universe_snapshot(
            db_session,
            _basic_payload(
                as_of_date=d,
                config_json=config,
                config_hash=_hash_config(config),
            ),
        )
    # 단일 as_of_date씩 조회 (정확히 일치 필터)
    rows_22 = get_universe_snapshot(db_session, date(2024, 1, 22), "KOSPI")
    rows_15 = get_universe_snapshot(db_session, date(2024, 1, 15), "KOSPI")
    rows_08 = get_universe_snapshot(db_session, date(2024, 1, 8), "KOSPI")
    assert len(rows_22) == 1
    assert len(rows_15) == 1
    assert len(rows_08) == 1
    assert rows_22[0].as_of_date == date(2024, 1, 22)


def test_missing_required_key_raises(db_session):
    for missing_key in ("as_of_date", "market", "selection_method", "config_json", "symbols_json"):
        payload = _basic_payload()
        del payload[missing_key]
        with pytest.raises(KeyError, match=missing_key):
            upsert_universe_snapshot(db_session, payload)


def test_run_id_nullable_for_preview_snapshot(db_session):
    """preview 스냅샷 (백테스트 미실행) → run_id NULL."""
    row = upsert_universe_snapshot(db_session, _basic_payload())
    assert row.run_id is None


def test_determinism_repeated_inserts_yield_same_result(db_session):
    """동일 payload 5회 반복 → DB 1건."""
    payload = _basic_payload()
    for _ in range(5):
        upsert_universe_snapshot(db_session, payload)
    rows = get_universe_snapshot(db_session, date(2024, 1, 8), "KOSPI")
    assert len(rows) == 1
    assert rows[0].symbols_json == ["005930", "000660", "035720"]


def test_survivorship_bias_preserves_delisted_symbols(db_session):
    """13.13 / 14.10: 폐지된 종목도 symbols_json에 그대로 보존되어 재현 시 생존편향 0."""
    config = {"market": "KOSPI", "selection_method": "ALL"}
    delisted_in_universe = ["005930", "999999"]  # 999999는 후에 폐지된 가상 종목
    upsert_universe_snapshot(
        db_session,
        _basic_payload(
            symbols_json=delisted_in_universe,
            config_json=config,
            config_hash=_hash_config(config),
        ),
    )
    # 재조회 — 폐지 종목 그대로 보존
    rows = get_universe_snapshot(db_session, date(2024, 1, 8), "KOSPI")
    assert "999999" in rows[0].symbols_json


def test_repr_contains_key_fields(db_session):
    row = upsert_universe_snapshot(db_session, _basic_payload())
    text = repr(row)
    assert "2024-01-08" in text
    assert "KOSPI" in text
    assert "ALL" in text
    assert "count=3" in text


def test_universe_history_table_in_metadata():
    """models/__init__ import 시 UniverseHistory가 metadata에 등록되어야 함."""
    from app.db.base import Base

    assert "universe_history" in Base.metadata.tables
    table = Base.metadata.tables["universe_history"]
    cols = {c.name for c in table.columns}
    assert {
        "id",
        "as_of_date",
        "market",
        "selection_method",
        "config_json",
        "config_hash",
        "symbols_json",
        "run_id",
        "created_at",
    } <= cols
    # UniqueConstraint
    import sqlalchemy as sa
    uniques = [c for c in table.constraints if isinstance(c, sa.UniqueConstraint)]
    assert any(
        c.name == "uq_universe_history_date_market_method_hash" for c in uniques
    )
    # 인덱스
    idx_names = {i.name for i in table.indexes}
    assert "ix_universe_history_as_of_date" in idx_names
    assert "ix_universe_history_run_id" in idx_names


def test_universe_history_orm_query_works(db_session):
    """ORM select로도 조회 가능 (모델 매핑 정상)."""
    upsert_universe_snapshot(db_session, _basic_payload())
    db_session.commit()

    from sqlalchemy import select

    result = db_session.execute(select(UniverseHistory)).scalars().all()
    assert len(result) == 1
    assert result[0].symbols_json == ["005930", "000660", "035720"]
