"""HistoricalBackfillJob 테스트 (Phase 11 step 028 / 14-j).

DailyUpdateJob과 흐름은 같지만 구간(start, end) 처리.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.data_pipeline.collectors.base import (
    BaseCollector,
    RawCalendarData,
    RawCalendarRow,
    RawDailyPriceRow,
    RawDailyPricesData,
    RawSymbolRow,
    RawSymbolsData,
)
from app.data_pipeline.jobs.historical_backfill import (
    HistoricalBackfillConfig,
    HistoricalBackfillJob,
)
from app.models.daily_price import DailyPrice


def _build_mock_collector(
    *,
    symbols: tuple[RawSymbolRow, ...] = (),
    prices: tuple[RawDailyPriceRow, ...] = (),
    calendar: tuple[RawCalendarRow, ...] = (),
    start: date = date(2024, 1, 1),
    end: date = date(2024, 1, 5),
) -> MagicMock:
    mock = MagicMock(spec=BaseCollector)
    mock.collect_symbols.return_value = RawSymbolsData(
        rows=symbols, as_of_date=end, source="mock"
    )
    mock.collect_daily_prices.return_value = RawDailyPricesData(
        rows=prices, start_date=start, end_date=end, source="mock"
    )
    mock.collect_trading_calendar.return_value = RawCalendarData(
        rows=calendar, start_date=start, end_date=end, market="KOSPI", source="mock"
    )
    return mock


def _make_symbol(code: str) -> RawSymbolRow:
    return RawSymbolRow(symbol=code, name=f"종목{code}", market="KOSPI", listing_date=date(2020, 1, 1))


def _make_price(code: str, d: date, close: float = 70_000.0) -> RawDailyPriceRow:
    return RawDailyPriceRow(
        symbol=code, date=d,
        open=close - 100, high=close + 200, low=close - 200, close=close, volume=1_000_000,
        adj_open=close - 100, adj_high=close + 200, adj_low=close - 200,
        adj_close=close, adj_volume=1_000_000,
        market_cap=close * 1_000_000_000,
    )


def test_backfill_persists_full_range(session_factory) -> None:
    start = date(2024, 1, 1)
    end = date(2024, 1, 5)
    symbols = (_make_symbol("005930"),)
    prices = (
        _make_price("005930", date(2024, 1, 2), 70_000),
        _make_price("005930", date(2024, 1, 3), 71_000),
        _make_price("005930", date(2024, 1, 4), 72_000),
    )
    calendar = (
        RawCalendarRow(date=date(2024, 1, 2), market="KOSPI", is_trading_day=True),
        RawCalendarRow(date=date(2024, 1, 3), market="KOSPI", is_trading_day=True),
        RawCalendarRow(date=date(2024, 1, 4), market="KOSPI", is_trading_day=True),
    )
    collector = _build_mock_collector(
        symbols=symbols, prices=prices, calendar=calendar, start=start, end=end
    )
    job = HistoricalBackfillJob(
        config=HistoricalBackfillConfig(
            start_date=start, end_date=end, markets=("KOSPI",)
        ),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    stats = dict(result.stats)
    assert stats["symbols_upserted"] == 1
    assert stats["trading_days_upserted"] == 3
    assert stats["daily_prices_upserted"] == 3
    assert stats["days_span"] == 5  # 2024-01-01 ~ 2024-01-05 (5일)

    session = session_factory()
    try:
        prices_in_db = session.query(DailyPrice).order_by(DailyPrice.date).all()
        assert [p.date for p in prices_in_db] == [
            date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)
        ]
    finally:
        session.close()


def test_backfill_passes_full_range_to_collector(session_factory) -> None:
    """collect_daily_prices에 (start, end) 그대로 전달."""
    start = date(2024, 1, 1)
    end = date(2024, 1, 31)
    collector = _build_mock_collector(
        symbols=(_make_symbol("005930"),),
        prices=(_make_price("005930", date(2024, 1, 2)),),
        start=start, end=end,
    )
    job = HistoricalBackfillJob(
        config=HistoricalBackfillConfig(
            start_date=start, end_date=end, markets=("KOSPI",)
        ),
        collector=collector,
        session_factory=session_factory,
    )
    job.run()

    args = collector.collect_daily_prices.call_args
    assert args.args[1] == start
    assert args.args[2] == end


def test_backfill_invalid_range_raises_in_config() -> None:
    """start > end → ValueError (config dataclass __post_init__)."""
    with pytest.raises(ValueError, match="start_date > end_date"):
        HistoricalBackfillConfig(
            start_date=date(2024, 1, 5), end_date=date(2024, 1, 1)
        )


def test_backfill_normalizes_collector_failure(session_factory) -> None:
    """collector raise → JobResult.success=False."""
    collector = _build_mock_collector(
        start=date(2024, 1, 1), end=date(2024, 1, 5)
    )
    collector.collect_daily_prices.side_effect = RuntimeError("API down")

    job = HistoricalBackfillJob(
        config=HistoricalBackfillConfig(
            start_date=date(2024, 1, 1), end_date=date(2024, 1, 5),
            markets=("KOSPI",),
            symbols=("005930",),  # 명시 → collect_daily_prices 호출됨
        ),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()
    assert result.success is False


def test_backfill_determinism_repeated_runs(session_factory) -> None:
    """동일 입력 두 번 실행 → 동일 stats."""
    start = date(2024, 1, 1)
    end = date(2024, 1, 5)
    collector = _build_mock_collector(
        symbols=(_make_symbol("005930"),),
        prices=(_make_price("005930", date(2024, 1, 2)),),
        start=start, end=end,
    )
    job = HistoricalBackfillJob(
        config=HistoricalBackfillConfig(
            start_date=start, end_date=end, markets=("KOSPI",)
        ),
        collector=collector,
        session_factory=session_factory,
    )
    r1 = job.run()
    r2 = job.run()
    assert r1.stats == r2.stats
