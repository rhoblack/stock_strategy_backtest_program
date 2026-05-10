"""CorporateAction 모델 + repositories CRUD 테스트 (07번 §12-B / 14번 §15).

검증 항목:
    - 기본 등록 / 조회
    - UniqueConstraint(symbol, event_date, event_type) — 동일 일자에
      split + cash_dividend 동시 가능
    - upsert 갱신 동작 (ratio / dividend_amount / notes)
    - get_corporate_actions 정렬 결정론 (event_date ASC, event_type ASC)
    - 알 수 없는 event_type → ValueError
    - 필수 키 누락 → KeyError
    - FK CASCADE — symbol 삭제 시 corporate_actions도 삭제
    - 결정론: 동일 입력 5회 반복 동일
"""

from __future__ import annotations

from datetime import date

import pytest

from app.market_data.repositories import (
    get_corporate_actions,
    upsert_corporate_action,
    upsert_symbol,
)
from app.models.corporate_action import (
    CORPORATE_ACTION_EVENT_TYPES,
    CorporateAction,
)


def _make_symbol(session, code="005930"):
    upsert_symbol(
        session,
        {
            "symbol": code,
            "name": "삼성전자",
            "market": "KOSPI",
            "listing_date": date(2000, 1, 1),
        },
    )


def test_upsert_corporate_action_creates_new(db_session):
    _make_symbol(db_session)
    row = upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2018, 5, 4),
            "event_type": "split",
            "ratio": 50.0,
            "notes": "삼성전자 50:1 액면분할",
        },
    )
    assert row.id is not None
    assert row.symbol == "005930"
    assert row.event_type == "split"
    assert row.ratio == 50.0
    assert row.dividend_amount is None
    assert row.notes == "삼성전자 50:1 액면분할"


def test_upsert_corporate_action_updates_existing(db_session):
    _make_symbol(db_session)
    upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2024, 5, 1),
            "event_type": "cash_dividend",
            "dividend_amount": 1000.0,
        },
    )
    # 동일 (symbol, event_date, event_type) 재호출 → 갱신
    updated = upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2024, 5, 1),
            "event_type": "cash_dividend",
            "dividend_amount": 1500.0,
            "notes": "정기배당 정정",
        },
    )
    assert updated.dividend_amount == 1500.0
    assert updated.notes == "정기배당 정정"

    # DB row 1건만
    rows = get_corporate_actions(db_session, "005930")
    assert len(rows) == 1
    assert rows[0].dividend_amount == 1500.0


def test_unique_constraint_allows_split_and_dividend_same_day(db_session):
    """동일 event_date에 event_type이 다르면 OK (예: 분할 + 배당 권리락 동일)."""
    _make_symbol(db_session)
    upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2024, 5, 1),
            "event_type": "split",
            "ratio": 2.0,
        },
    )
    upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2024, 5, 1),
            "event_type": "cash_dividend",
            "dividend_amount": 500.0,
        },
    )
    rows = get_corporate_actions(db_session, "005930")
    assert len(rows) == 2
    # 정렬: event_date ASC + event_type ASC ('cash_dividend' < 'split')
    assert rows[0].event_type == "cash_dividend"
    assert rows[1].event_type == "split"


def test_get_corporate_actions_orders_by_date_then_type(db_session):
    _make_symbol(db_session)
    upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2020, 3, 1),
            "event_type": "split",
            "ratio": 2.0,
        },
    )
    upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2018, 5, 4),
            "event_type": "split",
            "ratio": 50.0,
        },
    )
    upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2018, 5, 4),
            "event_type": "cash_dividend",
            "dividend_amount": 200.0,
        },
    )
    rows = get_corporate_actions(db_session, "005930")
    assert [(r.event_date, r.event_type) for r in rows] == [
        (date(2018, 5, 4), "cash_dividend"),
        (date(2018, 5, 4), "split"),
        (date(2020, 3, 1), "split"),
    ]


def test_get_corporate_actions_date_range_filter(db_session):
    _make_symbol(db_session)
    upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2018, 5, 4),
            "event_type": "split",
            "ratio": 50.0,
        },
    )
    upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2020, 3, 1),
            "event_type": "cash_dividend",
            "dividend_amount": 100.0,
        },
    )
    rows = get_corporate_actions(
        db_session, "005930", start_date=date(2019, 1, 1), end_date=date(2021, 12, 31)
    )
    assert len(rows) == 1
    assert rows[0].event_date == date(2020, 3, 1)


def test_unknown_event_type_raises(db_session):
    _make_symbol(db_session)
    with pytest.raises(ValueError, match="알 수 없는 event_type"):
        upsert_corporate_action(
            db_session,
            {
                "symbol": "005930",
                "event_date": date(2024, 1, 1),
                "event_type": "unknown_type",
            },
        )


def test_missing_required_key_raises(db_session):
    _make_symbol(db_session)
    with pytest.raises(KeyError, match="event_type"):
        upsert_corporate_action(
            db_session,
            {
                "symbol": "005930",
                "event_date": date(2024, 1, 1),
            },
        )


def test_fk_cascade_deletes_corporate_actions_on_symbol_delete(db_session):
    """symbols 삭제 시 corporate_actions도 자동 삭제 (ON DELETE CASCADE)."""
    # SQLite는 기본 FK 미강제이므로 명시적으로 켠다.
    db_session.execute(__import__("sqlalchemy").text("PRAGMA foreign_keys=ON"))

    _make_symbol(db_session, code="005930")
    upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2018, 5, 4),
            "event_type": "split",
            "ratio": 50.0,
        },
    )
    db_session.commit()

    # ORM cascade로 삭제 (관계 cascade='all, delete-orphan')
    from app.models.symbol import Symbol

    sym = db_session.get(Symbol, "005930")
    db_session.delete(sym)
    db_session.commit()

    rows = get_corporate_actions(db_session, "005930")
    assert rows == []


def test_event_types_enum_complete():
    """SUPPORTED enum은 14번 §15 + 13번 §7 정책 모든 종류 포함."""
    expected = {
        "split",
        "reverse_split",
        "bonus_issue",
        "rights_issue",
        "cash_dividend",
        "merger",
        "spinoff",
        "delisting",
    }
    assert set(CORPORATE_ACTION_EVENT_TYPES) == expected


def test_determinism_repeated_inserts_yield_same_result(db_session):
    """동일 입력 5회 반복 → DB 1건 + 동일 정렬 결과."""
    _make_symbol(db_session)
    payload = {
        "symbol": "005930",
        "event_date": date(2018, 5, 4),
        "event_type": "split",
        "ratio": 50.0,
    }
    for _ in range(5):
        upsert_corporate_action(db_session, payload)

    rows = get_corporate_actions(db_session, "005930")
    assert len(rows) == 1
    assert rows[0].ratio == 50.0


def test_repr_contains_key_fields(db_session):
    _make_symbol(db_session)
    row = upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2018, 5, 4),
            "event_type": "split",
            "ratio": 50.0,
        },
    )
    text = repr(row)
    assert "005930" in text
    assert "split" in text
    assert "ratio=50.0" in text

    row2 = upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2024, 5, 1),
            "event_type": "cash_dividend",
            "dividend_amount": 1000.0,
        },
    )
    text2 = repr(row2)
    assert "cash_dividend" in text2
    assert "dividend=1000.0" in text2


def test_corporate_action_table_in_metadata():
    """models/__init__ import 시 CorporateAction이 metadata에 등록되어야 함."""
    from app.db.base import Base

    assert "corporate_actions" in Base.metadata.tables
    table = Base.metadata.tables["corporate_actions"]
    cols = {c.name for c in table.columns}
    assert {
        "id",
        "symbol",
        "event_date",
        "event_type",
        "ratio",
        "dividend_amount",
        "notes",
        "created_at",
    } <= cols
    # UniqueConstraint
    uniques = [c for c in table.constraints if isinstance(c, __import__("sqlalchemy").UniqueConstraint)]
    assert any(c.name == "uq_corporate_actions_symbol_date_type" for c in uniques)
    # 인덱스
    idx_names = {i.name for i in table.indexes}
    assert "ix_corporate_actions_symbol_event_date" in idx_names


def test_corporate_action_orm_query_works(db_session):
    """ORM select로도 조회 가능 (모델 매핑 정상)."""
    _make_symbol(db_session)
    upsert_corporate_action(
        db_session,
        {
            "symbol": "005930",
            "event_date": date(2018, 5, 4),
            "event_type": "split",
            "ratio": 50.0,
        },
    )
    db_session.commit()

    from sqlalchemy import select

    result = db_session.execute(select(CorporateAction)).scalars().all()
    assert len(result) == 1
    assert result[0].ratio == 50.0
