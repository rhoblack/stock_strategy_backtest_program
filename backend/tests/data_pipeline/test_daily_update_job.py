"""DailyUpdateJob 증분 수집 테스트 (Phase 16 step 049 / 14-m).

신규 테스트 5개:
    - test_skips_nontrading_day: 비거래일이면 즉시 return
    - test_incremental_from_last_date: max(date) 기준 다음날부터 수집
    - test_no_op_when_up_to_date: 이미 당일 데이터 있으면 수집 안 함
    - test_corporate_action_triggers_recalc: corporate_action 발생 시 adj_* 재계산 호출
    - test_missing_data_check_called_after_update: run() 후 MissingDataCheckJob 호출 확인

14번 정책 매핑:
    - §6.2 (일일 증분) — 비거래일 체크 + max(date) 증분 판단
    - §9 (수정주가) — corporate_action 발생 시 AdjustedPriceProcessor 호출
    - §13 (결손 알림) — MissingDataCheckJob 연동
    - §15 (look-ahead) — as_of_date 이전 corporate_actions만 적용
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

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

# ---------------------------------------------------------------------------
# 헬퍼 함수
# ---------------------------------------------------------------------------


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


def _build_mock_collector(
    *,
    symbols: tuple[RawSymbolRow, ...] = (),
    prices: tuple[RawDailyPriceRow, ...] = (),
    calendar: tuple[RawCalendarRow, ...] = (),
    as_of: date = date(2024, 5, 2),
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


def _seed_trading_day(session_factory, d: date, market: str = "KOSPI", is_trading: bool = True) -> None:
    """거래일 캘린더 사전 삽입."""
    session = session_factory()
    try:
        repositories.upsert_trading_day(
            session, date=d, market=market, is_trading_day=is_trading
        )
        session.commit()
    finally:
        session.close()


def _seed_symbol_and_price(session_factory, code: str, d: date, close: float = 70_000.0) -> None:
    """symbol + daily_price 사전 삽입."""
    session = session_factory()
    try:
        repositories.upsert_symbol(
            session,
            {"symbol": code, "name": f"종목{code}", "market": "KOSPI", "listing_date": date(2020, 1, 1)},
        )
        repositories.bulk_upsert_daily_prices(
            session,
            rows=[
                {
                    "symbol": code,
                    "date": d,
                    "open": close - 100,
                    "high": close + 200,
                    "low": close - 200,
                    "close": close,
                    "volume": 1_000_000,
                    "adj_open": close - 100,
                    "adj_high": close + 200,
                    "adj_low": close - 200,
                    "adj_close": close,
                    "adj_volume": 1_000_000,
                    "market_cap": close * 1_000_000,
                }
            ],
        )
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 테스트 1: 비거래일 즉시 skip (14번 §6.2)
# ---------------------------------------------------------------------------


def test_skips_nontrading_day(session_factory) -> None:
    """거래일이 아닌 날 → run() 즉시 return (수집 skip).

    14번 §6.2: as_of_date가 거래일이 아니면 수집 전체 skip.
    trading_calendar에 is_trading_day=False로 등록된 날짜이면 즉시 no-op.
    """
    as_of = date(2024, 5, 4)  # 주말 (토요일)

    # 비거래일로 캘린더에 등록
    _seed_trading_day(session_factory, as_of, is_trading=False)

    collector = _build_mock_collector(as_of=as_of)
    job = DailyUpdateJob(
        config=DailyUpdateConfig(
            as_of_date=as_of,
            markets=("KOSPI",),
            check_trading_calendar=True,
            run_missing_data_check=False,
        ),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()

    # 수집 skip → success=True, collector 호출 없음
    assert result.success is True
    collector.collect_symbols.assert_not_called()
    collector.collect_daily_prices.assert_not_called()
    stats = dict(result.stats)
    assert stats["skipped_nontrading"] == 1
    assert stats["daily_prices_upserted"] == 0
    # 경고 메시지에 skip 사유 포함
    assert any("거래일이 아님" in w for w in result.warnings)


def test_skips_nontrading_day_calendar_missing(session_factory) -> None:
    """캘린더에 등록 자체가 없는 날짜 → False로 간주 → skip.

    14번 §6.2: 캘린더 결손 날짜는 안전 측 (거래일 아님)으로 간주.
    """
    as_of = date(2024, 5, 5)  # 캘린더에 없는 날

    collector = _build_mock_collector(as_of=as_of)
    job = DailyUpdateJob(
        config=DailyUpdateConfig(
            as_of_date=as_of,
            markets=("KOSPI",),
            check_trading_calendar=True,
            run_missing_data_check=False,
        ),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    collector.collect_symbols.assert_not_called()
    stats = dict(result.stats)
    assert stats["skipped_nontrading"] == 1


# ---------------------------------------------------------------------------
# 테스트 2: 증분 수집 — DB max(date) 기준 다음날부터 (14번 §6.2)
# ---------------------------------------------------------------------------


def test_incremental_from_last_date(session_factory) -> None:
    """DB에 5월 1일까지 데이터 있을 때 → 5월 2일을 수집 대상으로 판단.

    14번 §6.2 증분 판단:
        last = get_latest_price_date(session, symbol) → 2024-05-01
        as_of_date = 2024-05-02
        last < as_of_date → 수집 필요
    """
    as_of = date(2024, 5, 2)
    prev_date = date(2024, 5, 1)

    # 5월 1일까지 데이터 사전 삽입
    _seed_symbol_and_price(session_factory, "005930", prev_date, close=70_000.0)

    # 5월 2일 가격 mock
    prices = (_make_price("005930", as_of, 71_000.0),)
    collector = _build_mock_collector(
        symbols=(_make_symbol("005930"),),
        prices=prices,
        calendar=(RawCalendarRow(date=as_of, market="KOSPI", is_trading_day=True),),
        as_of=as_of,
    )
    job = DailyUpdateJob(
        config=DailyUpdateConfig(
            as_of_date=as_of,
            markets=("KOSPI",),
            incremental=True,
            check_trading_calendar=False,  # 캘린더 체크 없이 수집 진행
            run_missing_data_check=False,
        ),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    stats = dict(result.stats)
    # 005930이 last_date=2024-05-01 < as_of_date=2024-05-02 → 수집됨
    assert stats["daily_prices_upserted"] == 1
    assert stats["symbols_skipped_uptodate"] == 0

    # collector에 005930이 전달됐는지 확인
    collector.collect_daily_prices.assert_called_once()
    call_args = collector.collect_daily_prices.call_args
    assert "005930" in call_args.args[0]

    # DB에 5월 2일 데이터 있는지 확인
    session = session_factory()
    try:
        p = session.query(DailyPrice).filter_by(symbol="005930", date=as_of).first()
        assert p is not None
        assert p.close == 71_000.0
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 테스트 3: 이미 최신 데이터 있으면 수집 skip (14번 §6.2)
# ---------------------------------------------------------------------------


def test_no_op_when_up_to_date(session_factory) -> None:
    """이미 당일(as_of_date) 데이터 있으면 수집 skip.

    14번 §6.2:
        last = get_latest_price_date(session, symbol) = as_of_date
        last >= as_of_date → 수집 불필요 → symbols_skipped_uptodate += 1
    """
    as_of = date(2024, 5, 2)

    # 이미 당일 데이터 삽입
    _seed_symbol_and_price(session_factory, "005930", as_of, close=70_000.0)

    collector = _build_mock_collector(
        symbols=(_make_symbol("005930"),),
        prices=(_make_price("005930", as_of, 71_000.0),),
        as_of=as_of,
    )
    job = DailyUpdateJob(
        config=DailyUpdateConfig(
            as_of_date=as_of,
            markets=("KOSPI",),
            incremental=True,
            check_trading_calendar=False,
            run_missing_data_check=False,
        ),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    stats = dict(result.stats)
    # 이미 최신이므로 수집 skip
    assert stats["symbols_skipped_uptodate"] == 1
    assert stats["daily_prices_upserted"] == 0
    collector.collect_daily_prices.assert_not_called()

    # DB의 기존 가격(70000)이 유지됐는지 확인 (71000으로 덮어쓰지 않음)
    session = session_factory()
    try:
        p = session.query(DailyPrice).filter_by(symbol="005930", date=as_of).first()
        assert p is not None
        assert p.close == 70_000.0  # 원래 값 유지
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 테스트 4: corporate_action 발생 시 수정주가 재계산 호출 (14번 §9)
# ---------------------------------------------------------------------------


def test_corporate_action_triggers_recalc(session_factory) -> None:
    """당일 corporate_action 있는 종목 → AdjustedPriceProcessor.process() 호출 확인.

    14번 §9: corporate_actions 등록 시 adj_* 재계산.
    14번 §15 (look-ahead 차단): event_date <= as_of_date인 이벤트만 적용.
    """
    as_of = date(2024, 5, 2)

    # 사전 영속화: symbol + corporate_action 등록
    session = session_factory()
    try:
        repositories.upsert_symbol(
            session,
            {"symbol": "005930", "name": "삼성전자", "market": "KOSPI", "listing_date": date(2020, 1, 1)},
        )
        # event_date = 2024-04-30 (as_of_date 이전 → look-ahead OK)
        repositories.upsert_corporate_action(
            session,
            {
                "symbol": "005930",
                "event_date": date(2024, 4, 30),
                "event_type": "split",
                "ratio": 2.0,
            },
        )
        session.commit()
    finally:
        session.close()

    # AdjustedPriceProcessor를 spy로 교체
    spy_processor = MagicMock(
        wraps=__import__(
            "app.data_pipeline.processors.adjusted_price",
            fromlist=["AdjustedPriceProcessor"],
        ).AdjustedPriceProcessor()
    )

    prices = (_make_price("005930", as_of, 70_000.0),)
    collector = _build_mock_collector(
        symbols=(_make_symbol("005930"),),
        prices=prices,
        calendar=(RawCalendarRow(date=as_of, market="KOSPI", is_trading_day=True),),
        as_of=as_of,
    )
    job = DailyUpdateJob(
        config=DailyUpdateConfig(
            as_of_date=as_of,
            markets=("KOSPI",),
            apply_adjusted_price=True,
            incremental=False,  # 증분 없이 전체 수집
            check_trading_calendar=False,
            run_missing_data_check=False,
        ),
        collector=collector,
        session_factory=session_factory,
        processor=spy_processor,
    )
    result = job.run()

    assert result.success is True
    # AdjustedPriceProcessor.process 호출됐는지 확인
    spy_processor.process.assert_called_once()
    call_input = spy_processor.process.call_args.args[0]
    # corporate_actions가 전달됐는지 확인
    assert len(call_input.corporate_actions) >= 1
    ca_types = [ca.event_type for ca in call_input.corporate_actions]
    assert "split" in ca_types

    # 원 가격(close) 보존 확인
    session = session_factory()
    try:
        p = session.query(DailyPrice).filter_by(symbol="005930", date=as_of).first()
        assert p is not None
        assert p.close == 70_000.0  # 원 가격 보존
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 테스트 5: run() 후 MissingDataCheckJob 호출 확인 (14번 §13)
# ---------------------------------------------------------------------------


def test_missing_data_check_called_after_update(session_factory) -> None:
    """run() 후 MissingDataCheckJob이 호출됐는지 확인.

    14번 §13: 영속화 후 결손 알림 잡 실행.
    MissingDataCheckJob.run()이 실제로 호출됐는지 patch로 검증.
    """
    as_of = date(2024, 5, 2)

    # 거래일로 캘린더 등록 (MissingDataCheckJob이 조회)
    _seed_trading_day(session_factory, as_of, is_trading=True)

    prices = (_make_price("005930", as_of, 70_000.0),)
    collector = _build_mock_collector(
        symbols=(_make_symbol("005930"),),
        prices=prices,
        calendar=(RawCalendarRow(date=as_of, market="KOSPI", is_trading_day=True),),
        as_of=as_of,
    )

    with patch(
        "app.data_pipeline.jobs.daily_update.DailyUpdateJob._run_missing_data_check",
        return_value=0,
    ) as mock_check:
        job = DailyUpdateJob(
            config=DailyUpdateConfig(
                as_of_date=as_of,
                markets=("KOSPI",),
                incremental=False,
                check_trading_calendar=False,
                run_missing_data_check=True,  # 결손 체크 활성화
            ),
            collector=collector,
            session_factory=session_factory,
        )
        result = job.run()

    assert result.success is True
    # _run_missing_data_check 가 정확히 1회 호출됐는지 확인
    mock_check.assert_called_once()
    # stats에 missing_count 키 있는지 확인
    stats = dict(result.stats)
    assert "missing_count" in stats


def test_missing_data_check_integrates_with_real_job(session_factory) -> None:
    """MissingDataCheckJob 실제 호출 통합 테스트.

    run_missing_data_check=True + 실제 MissingDataCheckJob을 호출해
    결손 0건(당일 데이터가 있음)인지 확인.
    """
    as_of = date(2024, 5, 2)

    # 거래일 등록
    _seed_trading_day(session_factory, as_of, is_trading=True)

    prices = (_make_price("005930", as_of, 70_000.0),)
    collector = _build_mock_collector(
        symbols=(_make_symbol("005930"),),
        prices=prices,
        calendar=(RawCalendarRow(date=as_of, market="KOSPI", is_trading_day=True),),
        as_of=as_of,
    )
    job = DailyUpdateJob(
        config=DailyUpdateConfig(
            as_of_date=as_of,
            markets=("KOSPI",),
            symbols=("005930",),
            incremental=False,
            check_trading_calendar=False,
            run_missing_data_check=True,
        ),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    stats = dict(result.stats)
    # 일봉 1건 수집됐으므로 결손 0건
    assert stats["daily_prices_upserted"] == 1
    assert stats["missing_count"] == 0
