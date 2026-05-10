"""MarketIndex 모델 + repositories CRUD 테스트 (07번 §3 / 14번 §3-4 / 06번 §6).

검증 항목:
    - 기본 등록 / 조회
    - UniqueConstraint(index_code, date)
    - upsert 갱신 (open/high/low/close/volume/change_pct)
    - get_market_indices 정렬 (date ASC)
    - 알 수 없는 index_code → ValueError
    - 필수 키 누락 → KeyError
    - close NOT NULL, OHL/volume/change_pct는 NULL 허용
    - 결정론: 동일 입력 5회 반복 동일
    - models/__init__ 등록
"""

from __future__ import annotations

from datetime import date

import pytest

from app.market_data.repositories import (
    get_market_indices,
    upsert_market_index,
)
from app.models.market_index import MARKET_INDEX_CODES, MarketIndex


def test_upsert_market_index_creates_new(db_session):
    row = upsert_market_index(
        db_session,
        {
            "index_code": "KOSPI",
            "date": date(2024, 1, 2),
            "open": 2655.28,
            "high": 2670.10,
            "low": 2640.55,
            "close": 2669.81,
            "volume": 350_000_000.0,
            "change_pct": 0.55,
        },
    )
    assert row.id is not None
    assert row.index_code == "KOSPI"
    assert row.date == date(2024, 1, 2)
    assert row.close == 2669.81
    assert row.high == 2670.10
    assert row.change_pct == 0.55


def test_upsert_market_index_updates_existing(db_session):
    upsert_market_index(
        db_session,
        {
            "index_code": "KOSPI",
            "date": date(2024, 1, 2),
            "close": 2669.81,
        },
    )
    updated = upsert_market_index(
        db_session,
        {
            "index_code": "KOSPI",
            "date": date(2024, 1, 2),
            "close": 2670.00,  # 정정
            "change_pct": 0.56,
        },
    )
    assert updated.close == 2670.00
    assert updated.change_pct == 0.56

    rows = get_market_indices(db_session, "KOSPI")
    assert len(rows) == 1
    assert rows[0].close == 2670.00


def test_unique_constraint_per_index_code_and_date(db_session):
    """(index_code, date) 복합 UNIQUE — 다른 지수면 동일 일자 OK."""
    upsert_market_index(
        db_session,
        {
            "index_code": "KOSPI",
            "date": date(2024, 1, 2),
            "close": 2669.81,
        },
    )
    upsert_market_index(
        db_session,
        {
            "index_code": "KOSDAQ",
            "date": date(2024, 1, 2),
            "close": 878.93,
        },
    )
    kospi = get_market_indices(db_session, "KOSPI")
    kosdaq = get_market_indices(db_session, "KOSDAQ")
    assert len(kospi) == 1
    assert len(kosdaq) == 1
    assert kospi[0].close == 2669.81
    assert kosdaq[0].close == 878.93


def test_get_market_indices_orders_by_date(db_session):
    for d, c in [
        (date(2024, 1, 5), 2700.0),
        (date(2024, 1, 3), 2680.0),
        (date(2024, 1, 2), 2669.0),
        (date(2024, 1, 4), 2690.0),
    ]:
        upsert_market_index(
            db_session,
            {"index_code": "KOSPI", "date": d, "close": c},
        )
    rows = get_market_indices(db_session, "KOSPI")
    assert [r.date for r in rows] == [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    ]


def test_get_market_indices_date_range_filter(db_session):
    for d in [date(2024, 1, 2), date(2024, 1, 5), date(2024, 1, 10)]:
        upsert_market_index(
            db_session,
            {"index_code": "KOSPI", "date": d, "close": 2700.0},
        )
    rows = get_market_indices(
        db_session, "KOSPI",
        start_date=date(2024, 1, 3),
        end_date=date(2024, 1, 8),
    )
    assert len(rows) == 1
    assert rows[0].date == date(2024, 1, 5)


def test_unknown_index_code_raises(db_session):
    with pytest.raises(ValueError, match="알 수 없는 index_code"):
        upsert_market_index(
            db_session,
            {
                "index_code": "INVALID_INDEX",
                "date": date(2024, 1, 2),
                "close": 100.0,
            },
        )


def test_missing_required_key_raises(db_session):
    with pytest.raises(KeyError, match="close"):
        upsert_market_index(
            db_session,
            {
                "index_code": "KOSPI",
                "date": date(2024, 1, 2),
            },
        )
    with pytest.raises(KeyError, match="index_code"):
        upsert_market_index(
            db_session,
            {
                "date": date(2024, 1, 2),
                "close": 100.0,
            },
        )


def test_ohlcv_optional_fields_allow_null(db_session):
    """close 외 OHLCV/change_pct는 NULL 허용 (외부 데이터 결손 대응)."""
    row = upsert_market_index(
        db_session,
        {
            "index_code": "KOSPI200",
            "date": date(2024, 1, 2),
            "close": 360.50,
        },
    )
    assert row.open is None
    assert row.high is None
    assert row.low is None
    assert row.volume is None
    assert row.change_pct is None
    assert row.close == 360.50


def test_index_codes_enum_complete():
    """MARKET_INDEX_CODES enum은 14번 §3-4 정책 모든 지수 포함."""
    expected = {"KOSPI", "KOSDAQ", "KOSPI200", "KOSDAQ150", "KRX100"}
    assert set(MARKET_INDEX_CODES) == expected


def test_determinism_repeated_inserts_yield_same_result(db_session):
    """동일 입력 5회 반복 → DB 1건 + 동일 정렬 결과."""
    payload = {
        "index_code": "KOSPI",
        "date": date(2024, 1, 2),
        "close": 2669.81,
    }
    for _ in range(5):
        upsert_market_index(db_session, payload)
    rows = get_market_indices(db_session, "KOSPI")
    assert len(rows) == 1
    assert rows[0].close == 2669.81


def test_repr_contains_key_fields(db_session):
    row = upsert_market_index(
        db_session,
        {
            "index_code": "KOSPI",
            "date": date(2024, 1, 2),
            "close": 2669.81,
        },
    )
    text = repr(row)
    assert "KOSPI" in text
    assert "2024-01-02" in text
    assert "2669.81" in text


def test_market_index_table_in_metadata():
    """models/__init__ import 시 MarketIndex가 metadata에 등록되어야 함."""
    from app.db.base import Base

    assert "market_indices" in Base.metadata.tables
    table = Base.metadata.tables["market_indices"]
    cols = {c.name for c in table.columns}
    assert {
        "id",
        "index_code",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "change_pct",
        "created_at",
    } <= cols
    # UniqueConstraint
    import sqlalchemy as sa
    uniques = [c for c in table.constraints if isinstance(c, sa.UniqueConstraint)]
    assert any(c.name == "uq_market_indices_code_date" for c in uniques)
    # 인덱스
    idx_names = {i.name for i in table.indexes}
    assert "ix_market_indices_code_date" in idx_names


def test_market_index_orm_query_works(db_session):
    """ORM select로도 조회 가능 (모델 매핑 정상)."""
    upsert_market_index(
        db_session,
        {
            "index_code": "KOSPI",
            "date": date(2024, 1, 2),
            "close": 2669.81,
        },
    )
    db_session.commit()

    from sqlalchemy import select

    result = db_session.execute(select(MarketIndex)).scalars().all()
    assert len(result) == 1
    assert result[0].close == 2669.81
