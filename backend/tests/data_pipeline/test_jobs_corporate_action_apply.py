"""CorporateActionApplyJob 테스트 (Phase 11 step 028 / 14-j).

DB에 일봉 + corporate_actions 사전 영속화 → 잡 실행 → adj_* 재계산 검증.
forward-fill 금지 (결손 봉은 그대로).
"""

from __future__ import annotations

from datetime import date

import pytest

from app.data_pipeline.jobs.corporate_action_apply import (
    CorporateActionApplyConfig,
    CorporateActionApplyJob,
)
from app.market_data import repositories
from app.models.daily_price import DailyPrice


def _seed_symbol(session, code: str) -> None:
    repositories.upsert_symbol(
        session,
        {
            "symbol": code,
            "name": f"종목{code}",
            "market": "KOSPI",
            "listing_date": date(2020, 1, 1),
        },
    )


def _seed_prices(session, code: str, dates_and_closes: list[tuple[date, float]]) -> None:
    rows = []
    for d, c in dates_and_closes:
        rows.append({
            "symbol": code, "date": d,
            "open": c - 100, "high": c + 200, "low": c - 200, "close": c,
            "volume": 1_000_000,
            "adj_open": c - 100, "adj_high": c + 200, "adj_low": c - 200,
            "adj_close": c, "adj_volume": 1_000_000,
            "market_cap": c * 1_000_000_000,
        })
    repositories.bulk_upsert_daily_prices(session, rows)


def test_corporate_action_apply_split_recalculates_pre_event_prices(
    session_factory, db_session
) -> None:
    """1:2 분할 적용 시 분할 이전 가격이 1/2로 재계산되어 영속화."""
    code = "005930"
    _seed_symbol(db_session, code)
    # 분할 이전 봉 2건 + 분할 이후 봉 1건
    _seed_prices(db_session, code, [
        (date(2023, 12, 28), 70_000),
        (date(2023, 12, 29), 71_000),
        (date(2024, 1, 2), 35_500),  # 분할 후
    ])
    repositories.upsert_corporate_action(
        db_session,
        {
            "symbol": code,
            "event_date": date(2024, 1, 2),
            "event_type": "split",
            "ratio": 2.0,
        },
    )
    db_session.commit()

    job = CorporateActionApplyJob(
        config=CorporateActionApplyConfig(
            symbols=(code,),
            start_date=date(2023, 12, 1),
            end_date=date(2024, 1, 31),
        ),
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    stats = dict(result.stats)
    assert stats["symbols_processed"] == 1
    assert stats["rows_recalculated"] == 3
    assert stats["events_applied"] == 1

    session = session_factory()
    try:
        all_p = session.query(DailyPrice).order_by(DailyPrice.date).all()
        # close (원 가격) 보존
        assert [p.close for p in all_p] == [70_000.0, 71_000.0, 35_500.0]
        # adj_close — event_date(2024-01-02) 이전 가격에 1/2 적용
        assert all_p[0].adj_close == 35_000.0  # 2023-12-28
        assert all_p[1].adj_close == 35_500.0  # 2023-12-29
        # event_date 당일 봉은 변형 없음 (이전이 아니므로)
        assert all_p[2].adj_close == 35_500.0
    finally:
        session.close()


def test_corporate_action_apply_skips_symbols_with_no_actions(
    session_factory, db_session
) -> None:
    """corporate_actions 없는 종목은 skip — DB 변경 없음."""
    code = "000660"
    _seed_symbol(db_session, code)
    _seed_prices(db_session, code, [(date(2024, 1, 2), 130_000)])
    db_session.commit()

    job = CorporateActionApplyJob(
        config=CorporateActionApplyConfig(
            symbols=(code,),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        ),
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    assert dict(result.stats)["symbols_processed"] == 0
    assert any("corporate_actions 0건" in w for w in result.warnings)


def test_corporate_action_apply_skips_symbols_with_no_prices(
    session_factory, db_session
) -> None:
    """일봉 0건 → skip + 경고."""
    code = "005930"
    _seed_symbol(db_session, code)
    repositories.upsert_corporate_action(
        db_session,
        {
            "symbol": code,
            "event_date": date(2024, 1, 2),
            "event_type": "split",
            "ratio": 2.0,
        },
    )
    db_session.commit()

    job = CorporateActionApplyJob(
        config=CorporateActionApplyConfig(
            symbols=(code,),
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),  # 봉 없는 구간
        ),
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    assert dict(result.stats)["symbols_processed"] == 0
    assert any("재계산 범위에 일봉 0건" in w for w in result.warnings)


def test_corporate_action_apply_invalid_config() -> None:
    with pytest.raises(ValueError, match="symbols는 최소 1개"):
        CorporateActionApplyConfig(
            symbols=(), start_date=date(2024, 1, 1), end_date=date(2024, 1, 31)
        )
    with pytest.raises(ValueError, match="start_date > end_date"):
        CorporateActionApplyConfig(
            symbols=("005930",),
            start_date=date(2024, 1, 31),
            end_date=date(2024, 1, 1),
        )


def test_corporate_action_apply_determinism(session_factory, db_session) -> None:
    """동일 입력 두 번 실행 → DB 상태 동일 (idempotent)."""
    code = "005930"
    _seed_symbol(db_session, code)
    _seed_prices(db_session, code, [
        (date(2023, 12, 28), 70_000),
        (date(2024, 1, 2), 35_500),
    ])
    repositories.upsert_corporate_action(
        db_session,
        {
            "symbol": code, "event_date": date(2024, 1, 2),
            "event_type": "split", "ratio": 2.0,
        },
    )
    db_session.commit()

    job = CorporateActionApplyJob(
        config=CorporateActionApplyConfig(
            symbols=(code,),
            start_date=date(2023, 12, 1),
            end_date=date(2024, 1, 31),
        ),
        session_factory=session_factory,
    )
    r1 = job.run()
    r2 = job.run()
    assert r1.stats == r2.stats

    session = session_factory()
    try:
        p_pre = session.query(DailyPrice).filter_by(symbol=code, date=date(2023, 12, 28)).first()
        # 두 번째 호출 후에도 35_000 (재계산 결과 보존, 누적 적용 안 됨)
        assert p_pre.adj_close == 35_000.0
    finally:
        session.close()
