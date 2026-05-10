"""DailyUpdateJob 테스트 (Phase 11 step 028 / 14-j).

- mock collector 주입 (외부 fetch 0건)
- in-memory SQLite로 영속화 검증
- 결정론: 동일 입력 N회 반복 동일 결과
- adj_* 재계산: corporate_actions 등록 시 AdjustedPriceProcessor 호출 검증
- forward-fill 금지: collector가 결손 봉을 안 주면 DB에도 row 없음
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.data_pipeline.collectors.base import (
    BaseCollector,
    RawCalendarData,
    RawCalendarRow,
    RawDailyPriceRow,
    RawDailyPricesData,
    RawSymbolRow,
    RawSymbolsData,
)
from app.data_pipeline.jobs.daily_update import (
    DailyUpdateConfig,
    DailyUpdateJob,
)
from app.market_data import repositories
from app.models.daily_price import DailyPrice
from app.models.symbol import Symbol
from app.models.trading_calendar import TradingCalendar


def _build_mock_collector(
    *,
    symbols: tuple[RawSymbolRow, ...] = (),
    prices: tuple[RawDailyPriceRow, ...] = (),
    calendar: tuple[RawCalendarRow, ...] = (),
    as_of: date = date(2024, 1, 2),
) -> MagicMock:
    """3-메서드 mock collector — BaseCollector spec."""
    mock = MagicMock(spec=BaseCollector)
    mock.collect_symbols.return_value = RawSymbolsData(
        rows=symbols, as_of_date=as_of, source="mock"
    )
    mock.collect_daily_prices.return_value = RawDailyPricesData(
        rows=prices, start_date=as_of, end_date=as_of, source="mock"
    )
    mock.collect_trading_calendar.return_value = RawCalendarData(
        rows=calendar, start_date=as_of, end_date=as_of, market="KOSPI", source="mock"
    )
    return mock


def _make_symbol(code: str, market: str = "KOSPI", listing: date = date(2020, 1, 1)) -> RawSymbolRow:
    return RawSymbolRow(symbol=code, name=f"종목{code}", market=market, listing_date=listing)


def _make_price(code: str, d: date, close: float = 70_000.0) -> RawDailyPriceRow:
    return RawDailyPriceRow(
        symbol=code,
        date=d,
        open=close - 100,
        high=close + 200,
        low=close - 200,
        close=close,
        volume=1_000_000,
        adj_open=close - 100,
        adj_high=close + 200,
        adj_low=close - 200,
        adj_close=close,
        adj_volume=1_000_000,
        market_cap=close * 5_969_782_550,
    )


def test_daily_update_persists_symbols_calendar_prices(session_factory) -> None:
    """기본 흐름: 종목/거래일/일봉 모두 영속화."""
    as_of = date(2024, 1, 2)
    symbols = (_make_symbol("005930"), _make_symbol("000660"))
    prices = (
        _make_price("000660", as_of, 130_000),
        _make_price("005930", as_of, 70_000),
    )
    calendar = (
        RawCalendarRow(date=as_of, market="KOSPI", is_trading_day=True),
    )
    collector = _build_mock_collector(
        symbols=symbols, prices=prices, calendar=calendar, as_of=as_of
    )

    job = DailyUpdateJob(
        config=DailyUpdateConfig(as_of_date=as_of, markets=("KOSPI",)),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    assert result.errors == ()
    stats_dict = dict(result.stats)
    assert stats_dict["symbols_upserted"] == 2
    assert stats_dict["trading_days_upserted"] == 1
    assert stats_dict["daily_prices_upserted"] == 2
    assert stats_dict["events_applied"] == 0  # corporate_actions 없음

    # DB 검증
    session = session_factory()
    try:
        all_symbols = session.query(Symbol).order_by(Symbol.symbol).all()
        assert [s.symbol for s in all_symbols] == ["000660", "005930"]
        all_prices = session.query(DailyPrice).order_by(DailyPrice.symbol).all()
        assert [(p.symbol, p.date, p.close) for p in all_prices] == [
            ("000660", as_of, 130_000.0),
            ("005930", as_of, 70_000.0),
        ]
        cal = session.query(TradingCalendar).all()
        assert [(c.date, c.market, c.is_trading_day) for c in cal] == [
            (as_of, "KOSPI", True),
        ]
    finally:
        session.close()


def test_daily_update_calls_collector_per_market(session_factory) -> None:
    """markets=2개 시 collect_trading_calendar가 2회 호출."""
    as_of = date(2024, 1, 2)
    collector = _build_mock_collector(as_of=as_of)
    job = DailyUpdateJob(
        config=DailyUpdateConfig(as_of_date=as_of, markets=("KOSPI", "KOSDAQ")),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    assert collector.collect_symbols.call_count == 1
    assert collector.collect_trading_calendar.call_count == 2
    # 시장 인자 검증 (정렬 보장 X — config 순서 그대로)
    market_args = [c.args[2] for c in collector.collect_trading_calendar.call_args_list]
    assert set(market_args) == {"KOSPI", "KOSDAQ"}


def test_daily_update_skips_prices_when_no_symbols(session_factory) -> None:
    """대상 종목 0이면 collect_daily_prices 호출 안 함."""
    as_of = date(2024, 1, 2)
    collector = _build_mock_collector(as_of=as_of)
    job = DailyUpdateJob(
        config=DailyUpdateConfig(as_of_date=as_of, markets=("KOSPI",)),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    collector.collect_daily_prices.assert_not_called()
    assert dict(result.stats)["daily_prices_upserted"] == 0


def test_daily_update_uses_explicit_symbols_when_provided(session_factory) -> None:
    """config.symbols 명시 시 그것만 일봉 수집."""
    as_of = date(2024, 1, 2)
    # collect_symbols 결과에 005930이 포함되어 있어야 FK 제약 통과 (symbols 테이블에 먼저 upsert됨)
    collector = _build_mock_collector(
        symbols=(_make_symbol("005930"),),
        prices=(_make_price("005930", as_of),),
        as_of=as_of,
    )
    job = DailyUpdateJob(
        config=DailyUpdateConfig(
            as_of_date=as_of, markets=("KOSPI",), symbols=("005930",)
        ),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    collector.collect_daily_prices.assert_called_once()
    args = collector.collect_daily_prices.call_args
    assert args.args[0] == ("005930",)


def test_daily_update_applies_corporate_actions(session_factory) -> None:
    """corporate_actions 있는 종목은 AdjustedPriceProcessor 호출 (events_total > 0)."""
    as_of = date(2024, 1, 2)
    # 사전 영속화: corporate_actions 등록
    session = session_factory()
    try:
        repositories.upsert_symbol(
            session,
            {
                "symbol": "005930",
                "name": "삼성전자",
                "market": "KOSPI",
                "listing_date": date(2020, 1, 1),
            },
        )
        # event_date <= as_of_date (look-ahead OK).
        # 단, 본 잡은 단일 일자(as_of) 수집이므로 event_date(2023-12-01) "이전" 가격이 없어
        # adj_*는 변하지 않음. 본 테스트는 processor가 호출됐다는 사실만 검증.
        repositories.upsert_corporate_action(
            session,
            {
                "symbol": "005930",
                "event_date": date(2023, 12, 1),
                "event_type": "split",
                "ratio": 2.0,
            },
        )
        session.commit()
    finally:
        session.close()

    # processor를 spy로 교체
    spy_processor = MagicMock(wraps=__import__(
        "app.data_pipeline.processors.adjusted_price",
        fromlist=["AdjustedPriceProcessor"],
    ).AdjustedPriceProcessor())

    prices = (_make_price("005930", as_of, 70_000),)
    collector = _build_mock_collector(
        symbols=(_make_symbol("005930"),),
        prices=prices,
        calendar=(RawCalendarRow(date=as_of, market="KOSPI", is_trading_day=True),),
        as_of=as_of,
    )
    job = DailyUpdateJob(
        config=DailyUpdateConfig(as_of_date=as_of, markets=("KOSPI",)),
        collector=collector,
        session_factory=session_factory,
        processor=spy_processor,
    )
    result = job.run()

    assert result.success is True
    # processor.process가 호출됐는지 검증 (corporate_actions 1건 등록됐으므로)
    spy_processor.process.assert_called_once()
    call_input = spy_processor.process.call_args.args[0]
    assert len(call_input.corporate_actions) == 1
    assert call_input.corporate_actions[0].event_type == "split"

    # 원 가격 보존
    session = session_factory()
    try:
        p = session.query(DailyPrice).filter_by(symbol="005930", date=as_of).first()
        assert p is not None
        assert p.close == 70_000.0
    finally:
        session.close()


def test_daily_update_no_corporate_actions_passes_prices_through(session_factory) -> None:
    """corporate_actions 없으면 1차 adj_* 그대로 영속화."""
    as_of = date(2024, 1, 2)
    collector = _build_mock_collector(
        symbols=(_make_symbol("005930"),),
        prices=(_make_price("005930", as_of, 70_000),),
        calendar=(RawCalendarRow(date=as_of, market="KOSPI", is_trading_day=True),),
        as_of=as_of,
    )
    job = DailyUpdateJob(
        config=DailyUpdateConfig(as_of_date=as_of, markets=("KOSPI",)),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()
    assert result.success is True
    assert dict(result.stats)["events_applied"] == 0


def test_daily_update_skips_processor_when_apply_disabled(session_factory) -> None:
    """apply_adjusted_price=False면 corporate_actions 있어도 적용 안 함."""
    as_of = date(2024, 1, 2)
    session = session_factory()
    try:
        repositories.upsert_symbol(
            session, {"symbol": "005930", "name": "x", "market": "KOSPI", "listing_date": date(2020, 1, 1)}
        )
        repositories.upsert_corporate_action(
            session,
            {
                "symbol": "005930",
                "event_date": date(2023, 12, 1),
                "event_type": "split",
                "ratio": 2.0,
            },
        )
        session.commit()
    finally:
        session.close()

    collector = _build_mock_collector(
        symbols=(_make_symbol("005930"),),
        prices=(_make_price("005930", as_of, 70_000),),
        calendar=(RawCalendarRow(date=as_of, market="KOSPI", is_trading_day=True),),
        as_of=as_of,
    )
    job = DailyUpdateJob(
        config=DailyUpdateConfig(
            as_of_date=as_of, markets=("KOSPI",), apply_adjusted_price=False
        ),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()
    assert result.success is True

    session = session_factory()
    try:
        p = session.query(DailyPrice).filter_by(symbol="005930").first()
        assert p.adj_close == 70_000.0  # 재계산 안 됨 → 1차 adj_* 그대로
    finally:
        session.close()


def test_daily_update_normalizes_collector_failure_to_jobresult(session_factory) -> None:
    """collector raise → JobResult.success=False + errors 누적 (raise 안 됨)."""
    as_of = date(2024, 1, 2)
    collector = _build_mock_collector(as_of=as_of)
    collector.collect_symbols.side_effect = RuntimeError("pykrx 차단")

    job = DailyUpdateJob(
        config=DailyUpdateConfig(as_of_date=as_of, markets=("KOSPI",)),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is False
    assert any("RuntimeError" in e for e in result.errors)


def test_daily_update_clock_injection_is_deterministic(session_factory) -> None:
    """clock 주입으로 started_at/finished_at 결정론."""
    as_of = date(2024, 1, 2)
    fixed = datetime(2026, 5, 10, 18, 0, 0, tzinfo=UTC)
    collector = _build_mock_collector(as_of=as_of)
    job = DailyUpdateJob(
        config=DailyUpdateConfig(as_of_date=as_of, markets=("KOSPI",)),
        collector=collector,
        session_factory=session_factory,
        clock=lambda: fixed,
    )
    result = job.run()
    assert result.started_at == fixed
    assert result.finished_at == fixed
    assert result.duration_seconds == 0.0


def test_daily_update_determinism_repeated_runs_same_state(session_factory) -> None:
    """동일 입력 두 번 실행 — 두 번째 호출은 upsert(갱신)만 발생, DB 상태 동일."""
    as_of = date(2024, 1, 2)
    symbols = (_make_symbol("005930"),)
    prices = (_make_price("005930", as_of, 70_000),)
    calendar = (RawCalendarRow(date=as_of, market="KOSPI", is_trading_day=True),)
    collector = _build_mock_collector(
        symbols=symbols, prices=prices, calendar=calendar, as_of=as_of
    )

    job = DailyUpdateJob(
        config=DailyUpdateConfig(as_of_date=as_of, markets=("KOSPI",)),
        collector=collector,
        session_factory=session_factory,
    )
    r1 = job.run()
    r2 = job.run()

    assert r1.success is True and r2.success is True
    assert r1.stats == r2.stats  # 결정론

    session: Session = session_factory()
    try:
        prices_count = session.query(DailyPrice).count()
        assert prices_count == 1  # 갱신만, 중복 row 없음
    finally:
        session.close()


def test_daily_update_jobresult_stats_are_sorted_tuple(session_factory) -> None:
    """JobResult.stats는 (key ASC) 정렬 tuple — 결정론."""
    as_of = date(2024, 1, 2)
    collector = _build_mock_collector(as_of=as_of)
    job = DailyUpdateJob(
        config=DailyUpdateConfig(as_of_date=as_of, markets=("KOSPI",)),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()
    keys = [k for k, _ in result.stats]
    assert keys == sorted(keys)
