"""MissingDataCheckJob 테스트 (Phase 11 step 028 / 14-k).

is_trading_day=true인데 daily_prices에 row가 없으면 MissingDataAlert.
forward-fill 절대 금지 (14.10) — 본 잡은 결손을 만들지도 채우지도 않음.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.data_pipeline.jobs.missing_data_check import (
    MissingDataAlert,
    MissingDataCheckConfig,
    MissingDataCheckJob,
    MissingDataEntry,
)
from app.market_data import repositories


def _seed_calendar(session, dates: list[date], market: str = "KOSPI") -> None:
    for d in dates:
        repositories.upsert_trading_day(
            session, date=d, market=market, is_trading_day=True
        )


def _seed_holiday(session, d: date, name: str, market: str = "KOSPI") -> None:
    repositories.upsert_trading_day(
        session, date=d, market=market, is_trading_day=False, holiday_name=name
    )


def _seed_symbol(session, code: str, market: str = "KOSPI") -> None:
    repositories.upsert_symbol(
        session,
        {
            "symbol": code, "name": f"종목{code}",
            "market": market, "listing_date": date(2020, 1, 1),
        },
    )


def _seed_price(session, code: str, d: date, close: float = 70_000.0) -> None:
    repositories.bulk_upsert_daily_prices(
        session,
        [{
            "symbol": code, "date": d,
            "open": close - 100, "high": close + 200, "low": close - 200, "close": close,
            "volume": 1_000_000,
            "adj_open": close - 100, "adj_high": close + 200, "adj_low": close - 200,
            "adj_close": close, "adj_volume": 1_000_000,
        }],
    )


def test_missing_data_detects_no_missing_when_all_present(
    session_factory, db_session
) -> None:
    """모든 거래일에 봉이 있으면 결손 0건."""
    days = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    _seed_calendar(db_session, days)
    _seed_symbol(db_session, "005930")
    for d in days:
        _seed_price(db_session, "005930", d)
    db_session.commit()

    job = MissingDataCheckJob(
        config=MissingDataCheckConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            market="KOSPI",
            symbols=("005930",),
        ),
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    stats = dict(result.stats)
    assert stats["trading_days"] == 3
    assert stats["missing_count"] == 0
    assert stats["missing_symbols"] == 0
    assert job.last_alert.missing_count == 0
    assert job.last_alert.entries == ()


def test_missing_data_detects_missing_days(session_factory, db_session) -> None:
    """봉이 없는 거래일은 결손으로 잡힌다 (forward-fill 금지)."""
    days = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    _seed_calendar(db_session, days)
    _seed_symbol(db_session, "005930")
    # 1/2만 있음. 1/3, 1/4 결손.
    _seed_price(db_session, "005930", date(2024, 1, 2))
    db_session.commit()

    job = MissingDataCheckJob(
        config=MissingDataCheckConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            market="KOSPI",
            symbols=("005930",),
        ),
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    stats = dict(result.stats)
    assert stats["missing_count"] == 2
    assert stats["missing_symbols"] == 1

    alert = job.last_alert
    assert alert.missing_count == 2
    assert alert.entries == (
        MissingDataEntry(symbol="005930", date=date(2024, 1, 3), market="KOSPI"),
        MissingDataEntry(symbol="005930", date=date(2024, 1, 4), market="KOSPI"),
    )
    assert any("결손 감지" in w for w in result.warnings)


def test_missing_data_does_not_count_holidays(session_factory, db_session) -> None:
    """is_trading_day=false인 날짜는 결손 아님 (휴장일)."""
    _seed_calendar(db_session, [date(2024, 1, 2), date(2024, 1, 4)])
    _seed_holiday(db_session, date(2024, 1, 3), "임시 휴장")  # 휴장일
    _seed_symbol(db_session, "005930")
    _seed_price(db_session, "005930", date(2024, 1, 2))
    _seed_price(db_session, "005930", date(2024, 1, 4))
    db_session.commit()

    job = MissingDataCheckJob(
        config=MissingDataCheckConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            market="KOSPI",
            symbols=("005930",),
        ),
        session_factory=session_factory,
    )
    result = job.run()
    assert result.success is True
    assert dict(result.stats)["missing_count"] == 0


def test_missing_data_uses_active_symbols_when_unspecified(
    session_factory, db_session
) -> None:
    """config.symbols=None이면 활성 종목 전체 검사."""
    _seed_calendar(db_session, [date(2024, 1, 2)])
    _seed_symbol(db_session, "005930")
    _seed_symbol(db_session, "000660")
    # 005930만 봉 있음
    _seed_price(db_session, "005930", date(2024, 1, 2))
    db_session.commit()

    job = MissingDataCheckJob(
        config=MissingDataCheckConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 2),
            market="KOSPI",
            symbols=None,  # 활성 종목 전체
        ),
        session_factory=session_factory,
    )
    result = job.run()
    assert result.success is True
    stats = dict(result.stats)
    assert stats["symbols_checked"] == 2  # 005930 + 000660
    assert stats["missing_count"] == 1   # 000660만 결손
    assert stats["missing_symbols"] == 1


def test_missing_data_no_trading_days_warns(session_factory) -> None:
    """검사 구간에 거래일 0건 → warnings."""
    job = MissingDataCheckJob(
        config=MissingDataCheckConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            market="KOSPI",
        ),
        session_factory=session_factory,
    )
    result = job.run()
    assert result.success is True
    assert any("거래일 0건" in w for w in result.warnings)
    assert dict(result.stats)["trading_days"] == 0


def test_missing_data_alert_entries_are_sorted(session_factory, db_session) -> None:
    """alert.entries는 (symbol ASC, date ASC) 정렬."""
    days = [date(2024, 1, 2), date(2024, 1, 3)]
    _seed_calendar(db_session, days)
    _seed_symbol(db_session, "005930")
    _seed_symbol(db_session, "000660")
    db_session.commit()
    # 모든 종목 모든 날짜 결손

    job = MissingDataCheckJob(
        config=MissingDataCheckConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            market="KOSPI",
            symbols=("005930", "000660"),
        ),
        session_factory=session_factory,
    )
    job.run()
    entries = job.last_alert.entries
    assert [(e.symbol, e.date) for e in entries] == [
        ("000660", date(2024, 1, 2)),
        ("000660", date(2024, 1, 3)),
        ("005930", date(2024, 1, 2)),
        ("005930", date(2024, 1, 3)),
    ]


def test_missing_data_invalid_config_raises() -> None:
    with pytest.raises(ValueError, match="start_date > end_date"):
        MissingDataCheckConfig(
            start_date=date(2024, 1, 31), end_date=date(2024, 1, 1)
        )


def test_missing_data_does_not_forward_fill(session_factory, db_session) -> None:
    """결손은 그대로 보존 — 잡 실행 후에도 daily_prices row는 추가되지 않음 (14.10)."""
    days = [date(2024, 1, 2), date(2024, 1, 3)]
    _seed_calendar(db_session, days)
    _seed_symbol(db_session, "005930")
    _seed_price(db_session, "005930", date(2024, 1, 2))  # 1/3 결손
    db_session.commit()

    # 결손 전 row 카운트
    pre_count = repositories.get_price_range(
        db_session, symbol="005930",
        start_date=date(2024, 1, 1), end_date=date(2024, 1, 5)
    )
    assert len(pre_count) == 1

    job = MissingDataCheckJob(
        config=MissingDataCheckConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            market="KOSPI",
            symbols=("005930",),
        ),
        session_factory=session_factory,
    )
    result = job.run()
    assert result.success is True
    assert dict(result.stats)["missing_count"] == 1

    # 잡 실행 후에도 row 수는 동일 (forward-fill 금지)
    session = session_factory()
    try:
        post_count = repositories.get_price_range(
            session, symbol="005930",
            start_date=date(2024, 1, 1), end_date=date(2024, 1, 5)
        )
        assert len(post_count) == 1
    finally:
        session.close()


def test_missing_data_alert_dataclass_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    alert = MissingDataAlert(
        entries=(MissingDataEntry(symbol="005930", date=date(2024, 1, 2), market="KOSPI"),),
        total_trading_days=1,
        total_symbols=1,
        as_of_market="KOSPI",
    )
    with pytest.raises(FrozenInstanceError):
        alert.entries = ()  # type: ignore[misc]
