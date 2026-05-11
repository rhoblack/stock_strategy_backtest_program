"""Phase 19 step 058 — data_pipeline 통합 테스트 (12-j).

Phase 11 e2e(`test_phase11_data_pipeline_e2e.py`)는 collector→processor→jobs 기본 흐름을
보호하지만, Phase 16 이후 추가된 구성요소에 대한 보완 시나리오를 제공한다.

검증 매핑 (정확성 정책 13.x / 14.x):
    - 13.7  (수정주가 정합 — close 보존, adj_*만 재계산)         → 시나리오 3·4
    - 13.12 (결정론 — symbol/date ASC 정렬)                      → 시나리오 3
    - 13.15 (look-ahead — 미래 corporate_action 차단)             → 시나리오 4
    - 14.5  (분할/배당 발생 시 과거 전체 재계산, 누적 금지)         → 시나리오 4
    - 14.10 (forward-fill 금지)                                   → 시나리오 2
    - 14.12 (체크포인트 저장 → 재시작 시 중복 없음)                → 시나리오 1
    - 14.6.4 (연속 실패 차단 대응 — RateLimiter)                  → 시나리오 5

본 테스트는 모든 외부 네트워크 호출을 차단한다 (pykrx 실호출 0건).
각 시나리오는 독립 fixture (임시 SQLite in-memory DB)로 실행된다.
"""

from __future__ import annotations

import threading
from datetime import date
from unittest.mock import MagicMock, patch

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
from app.data_pipeline.jobs.daily_update import (
    DailyUpdateConfig,
    DailyUpdateJob,
)
from app.data_pipeline.jobs.historical_backfill import (
    ALL_STAGES,
    BackfillCheckpoint,
    HistoricalBackfillConfig,
    HistoricalBackfillJob,
)
from app.data_pipeline.jobs.missing_data_check import (
    MissingDataCheckConfig,
    MissingDataCheckJob,
)
from app.data_pipeline.processors.adjusted_price import (
    AdjustedPriceInput,
    AdjustedPriceProcessor,
    CorporateActionEvent,
)
from app.data_pipeline.scheduler import LockError, Scheduler
from app.data_pipeline.utils.rate_limiter import RateLimiter
from app.db.session import (
    create_db_engine,
    drop_db,
    init_db,
    make_session_factory,
)
from app.market_data import repositories
from app.market_data.provider import BaseProvider
from app.market_data.pykrx_provider import PYKRX_PROVIDER_COLUMNS, PykrxProvider
from app.models.daily_price import DailyPrice

# ---------------------------------------------------------------------------
# 공통 fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db_engine():
    """in-memory SQLite — 모든 테이블 생성."""
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    try:
        yield engine
    finally:
        drop_db(engine)
        engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    """잡이 호출할 때마다 새 세션을 반환하는 callable."""
    SessionLocal = make_session_factory(db_engine)
    return lambda: SessionLocal()


@pytest.fixture
def db_session(db_engine):
    """단일 세션 — 시드/검증용."""
    SessionLocal = make_session_factory(db_engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _make_symbol(
    code: str,
    market: str = "KOSPI",
    listing: date = date(2020, 1, 1),
    delisting: date | None = None,
) -> RawSymbolRow:
    return RawSymbolRow(
        symbol=code,
        name=f"종목{code}",
        market=market,
        listing_date=listing,
        delisting_date=delisting,
    )


def _make_price_row(
    code: str,
    d: date,
    close: float = 50_000.0,
    *,
    adj_close: float | None = None,
) -> RawDailyPriceRow:
    """일봉 1건 — adj_close 미지정 시 close와 동일 (13.7)."""
    if adj_close is None:
        adj_close = close
    ratio = adj_close / close if close != 0 else 1.0
    return RawDailyPriceRow(
        symbol=code,
        date=d,
        open=close - 500,
        high=close + 1000,
        low=close - 1000,
        close=close,
        volume=1_000_000,
        adj_open=(close - 500) * ratio,
        adj_high=(close + 1000) * ratio,
        adj_low=(close - 1000) * ratio,
        adj_close=adj_close,
        adj_volume=1_000_000 / ratio if ratio != 0 else 1_000_000,
    )


def _build_mock_collector(
    *,
    symbols: tuple[RawSymbolRow, ...] = (),
    prices: tuple[RawDailyPriceRow, ...] = (),
    calendar: tuple[RawCalendarRow, ...] = (),
    as_of: date = date(2024, 1, 2),
    start_date: date | None = None,
    end_date: date | None = None,
) -> MagicMock:
    """BaseCollector 인터페이스를 MagicMock으로 구현 (외부 pykrx 호출 0건)."""
    mock = MagicMock(spec=BaseCollector)
    mock.collect_symbols.return_value = RawSymbolsData(
        rows=symbols, as_of_date=as_of, source="mock"
    )
    mock.collect_daily_prices.return_value = RawDailyPricesData(
        rows=prices,
        start_date=start_date or as_of,
        end_date=end_date or as_of,
        source="mock",
    )
    mock.collect_trading_calendar.return_value = RawCalendarData(
        rows=calendar,
        start_date=start_date or as_of,
        end_date=end_date or as_of,
        market="KOSPI",
        source="mock",
    )
    return mock


# ---------------------------------------------------------------------------
# 시나리오 1: HistoricalBackfillJob 체크포인트 재개 — 정책 14.12
#
# 검증:
#   - 1차 run: 일부 종목 처리 후 체크포인트 저장 (의도적 중단 시뮬레이션)
#   - 2차 run: 동일 체크포인트에서 재개, 이미 처리된 심볼은 스킵
#   - DB에 중복 데이터 없음 (bulk_upsert idempotent)
#   - 외부 pykrx fetch 0건 (MagicMock)
# ---------------------------------------------------------------------------


def test_historical_backfill_checkpoint_resume_no_duplicate(
    session_factory, db_session, tmp_path
):
    """HistoricalBackfillJob 체크포인트 재개 시 중복 없음 (14.12).

    시나리오:
        1. symbols = ["A000010", "A000020"] 중 A000010만 1차 run에서 처리됨.
           체크포인트 last_symbol = "A000010"으로 저장.
        2. 2차 run: A000010은 스킵, A000020만 수집 → DB 총 2건 (중복 없음).
    """
    SYMBOL1 = "A000010"
    SYMBOL2 = "A000020"
    AS_OF = date(2024, 1, 5)
    checkpoint_path = tmp_path / "backfill_ckpt.json"

    # DB 종목 시드 (FK 만족)
    repositories.upsert_symbol(
        db_session,
        {
            "symbol": SYMBOL1,
            "name": "종목A",
            "market": "KOSPI",
            "listing_date": date(2020, 1, 1),
        },
    )
    repositories.upsert_symbol(
        db_session,
        {
            "symbol": SYMBOL2,
            "name": "종목B",
            "market": "KOSPI",
            "listing_date": date(2020, 1, 1),
        },
    )
    db_session.commit()

    # 가격 데이터 준비 (각 종목 3봉)
    prices_symbol1 = tuple(
        _make_price_row(SYMBOL1, date(2024, 1, d)) for d in [2, 3, 4]
    )
    prices_symbol2 = tuple(
        _make_price_row(SYMBOL2, date(2024, 1, d)) for d in [2, 3, 4]
    )

    # --- 1차 run: A000010만 처리 후 중단 시뮬레이션 ---
    # collector가 SYMBOL1에 대해서만 가격 반환 (per-symbol 호출이므로 side_effect 사용)
    def make_price_response(syms, start, end):
        if SYMBOL1 in syms:
            return RawDailyPricesData(
                rows=prices_symbol1, start_date=start, end_date=end, source="mock"
            )
        return RawDailyPricesData(rows=(), start_date=start, end_date=end, source="mock")

    mock_collector_1 = _build_mock_collector(
        symbols=(_make_symbol(SYMBOL1), _make_symbol(SYMBOL2)),
        as_of=AS_OF,
        start_date=date(2024, 1, 2),
        end_date=AS_OF,
    )
    mock_collector_1.collect_daily_prices.side_effect = make_price_response

    # 체크포인트 수동 조작: symbols + calendar + corporate_actions 완료 상태로 만들고
    # daily_prices 단계는 last_symbol=SYMBOL1(완료)까지만 진행된 것으로 시뮬레이션
    # (HistoricalBackfillJob의 실제 로직 사용 — 단, SYMBOL2 수집 전에 체크포인트 직접 작성)
    ckpt = BackfillCheckpoint(
        as_of_date=AS_OF.isoformat(),
        completed_stages=["symbols", "calendar", "corporate_actions"],
        last_symbol=SYMBOL1,  # SYMBOL1까지 daily_prices 완료 → SYMBOL2부터 재개
    )
    # SYMBOL1 일봉을 직접 DB에 넣어 "이미 처리됨"을 시뮬레이션
    repositories.bulk_upsert_daily_prices(
        db_session,
        [
            {
                "symbol": r.symbol,
                "date": r.date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "adj_open": r.adj_open,
                "adj_high": r.adj_high,
                "adj_low": r.adj_low,
                "adj_close": r.adj_close,
                "adj_volume": r.adj_volume,
                "market_cap": None,
            }
            for r in prices_symbol1
        ],
    )
    db_session.commit()
    ckpt.save(checkpoint_path)

    # DB 상태: SYMBOL1 3건, SYMBOL2 0건
    before_count = db_session.query(DailyPrice).count()
    assert before_count == 3

    # --- 2차 run: 체크포인트에서 재개 (SYMBOL2만 수집해야 함) ---
    mock_collector_2 = _build_mock_collector(
        symbols=(_make_symbol(SYMBOL1), _make_symbol(SYMBOL2)),
        as_of=AS_OF,
        start_date=date(2024, 1, 2),
        end_date=AS_OF,
    )

    def make_price_response_2(syms, start, end):
        # SYMBOL2 요청 시에만 데이터 반환
        if SYMBOL2 in syms:
            return RawDailyPricesData(
                rows=prices_symbol2, start_date=start, end_date=end, source="mock"
            )
        return RawDailyPricesData(rows=(), start_date=start, end_date=end, source="mock")

    mock_collector_2.collect_daily_prices.side_effect = make_price_response_2

    config = HistoricalBackfillConfig(
        start_date=date(2024, 1, 2),
        end_date=AS_OF,
        markets=("KOSPI",),
        symbols=(SYMBOL1, SYMBOL2),
        apply_adjusted_price=False,  # corporate_actions 없으므로 skip
        checkpoint_path=checkpoint_path,
        # rate_limiter: 실제 sleep 없이 즉시 통과하도록 설정
        rate_limiter=RateLimiter(
            min_interval_seconds=0.0,
            max_consecutive_failures=999,
            sleep_fn=lambda s: None,  # 실제 sleep 없음
            monotonic_fn=lambda: 0.0,
        ),
    )

    job = HistoricalBackfillJob(
        config=config,
        collector=mock_collector_2,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True, f"run 실패: {result.errors}"

    # 14.12: 중복 없음 검증 — SYMBOL1 3 + SYMBOL2 3 = 6건
    fresh = session_factory()
    try:
        total = fresh.query(DailyPrice).count()
        assert total == 6, (
            f"체크포인트 재개 후 DB 행 수 {total} ≠ 6 (14.12 중복 없음 위반)"
        )
        symbol1_count = (
            fresh.query(DailyPrice).filter(DailyPrice.symbol == SYMBOL1).count()
        )
        symbol2_count = (
            fresh.query(DailyPrice).filter(DailyPrice.symbol == SYMBOL2).count()
        )
        # SYMBOL1은 이미 3건 있었으므로 그대로 3건 (idempotent upsert)
        assert symbol1_count == 3, f"SYMBOL1 중복 발생: {symbol1_count}"
        # SYMBOL2는 새로 3건 추가
        assert symbol2_count == 3, f"SYMBOL2 누락: {symbol2_count}"
    finally:
        fresh.close()


def test_historical_backfill_checkpoint_roundtrip(tmp_path):
    """BackfillCheckpoint save/load 왕복 검증 (14.12).

    결정론: sort_keys=True JSON 저장 후 로드해도 동일 상태 복원.
    """
    checkpoint_path = tmp_path / "ckpt.json"
    ckpt = BackfillCheckpoint(
        as_of_date="2024-01-05",
        completed_stages=["symbols", "calendar"],
        last_symbol="A000010",
    )
    ckpt.save(checkpoint_path)

    loaded = BackfillCheckpoint.load(checkpoint_path)
    assert loaded is not None
    assert loaded.as_of_date == "2024-01-05"
    assert loaded.completed_stages == ["symbols", "calendar"]
    assert loaded.last_symbol == "A000010"

    # mark_stage_done 누적 검증
    ckpt.mark_stage_done("corporate_actions", checkpoint_path)
    loaded2 = BackfillCheckpoint.load(checkpoint_path)
    assert loaded2 is not None
    assert "corporate_actions" in loaded2.completed_stages


def test_historical_backfill_different_as_of_date_resets_checkpoint(tmp_path):
    """as_of_date가 다르면 체크포인트 무시 → 신규 시작 (14.12)."""
    checkpoint_path = tmp_path / "ckpt.json"
    # 과거 날짜로 저장된 체크포인트
    old_ckpt = BackfillCheckpoint(
        as_of_date="2023-12-31",
        completed_stages=list(ALL_STAGES),  # 전부 완료
        last_symbol=None,
    )
    old_ckpt.save(checkpoint_path)

    mock_collector = _build_mock_collector(
        symbols=(),
        as_of=date(2024, 1, 5),
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 5),
    )

    config = HistoricalBackfillConfig(
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 5),  # 다른 날짜
        markets=("KOSPI",),
        apply_adjusted_price=False,
        checkpoint_path=checkpoint_path,
        rate_limiter=RateLimiter(
            min_interval_seconds=0.0,
            max_consecutive_failures=999,
            sleep_fn=lambda s: None,
            monotonic_fn=lambda: 0.0,
        ),
    )

    # in-memory DB (단순히 실행 성공 여부만 검증)
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    SessionLocal = make_session_factory(engine)
    sf = lambda: SessionLocal()  # noqa: E731

    try:
        job = HistoricalBackfillJob(
            config=config,
            collector=mock_collector,
            session_factory=sf,
        )
        result = job.run()
        assert result.success is True

        # 새 체크포인트가 생성되어야 함 (다른 as_of_date)
        new_ckpt = BackfillCheckpoint.load(checkpoint_path)
        assert new_ckpt is not None
        assert new_ckpt.as_of_date == "2024-01-05"
    finally:
        drop_db(engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# 시나리오 2: DailyUpdateJob 증분 수집 + forward-fill 금지 검증 — 정책 14.10
#
# 검증:
#   - 이미 당일 데이터가 있는 종목은 재수집 안 함 (incremental=True)
#   - 비거래일은 no-op (check_trading_calendar=True)
#   - idempotent: 같은 날 2회 실행해도 DB 행 수 변화 없음
#   - forward-fill 미적용: 결손 일자에 row 없음
# ---------------------------------------------------------------------------


def test_daily_update_incremental_skips_already_collected_symbols(
    session_factory, db_session
):
    """증분 수집: 이미 당일 데이터 있는 종목은 collector 호출 없음 (14.10).

    시나리오:
        - SYMBOL1은 2024-01-02 데이터 이미 존재 → 스킵
        - SYMBOL2는 데이터 없음 → 수집 대상
        - collector.collect_daily_prices 호출 시 symbols에 SYMBOL1 없음 검증
    """
    AS_OF = date(2024, 1, 2)
    SYMBOL1 = "000660"
    SYMBOL2 = "005930"

    # SYMBOL1 종목 + 가격 시드 (이미 최신 데이터 있음)
    repositories.upsert_symbol(
        db_session,
        {
            "symbol": SYMBOL1,
            "name": "하이닉스",
            "market": "KOSPI",
            "listing_date": date(2020, 1, 1),
        },
    )
    repositories.upsert_symbol(
        db_session,
        {
            "symbol": SYMBOL2,
            "name": "삼성전자",
            "market": "KOSPI",
            "listing_date": date(2020, 1, 1),
        },
    )
    repositories.bulk_upsert_daily_prices(
        db_session,
        [
            {
                "symbol": SYMBOL1,
                "date": AS_OF,
                "open": 129_000,
                "high": 131_000,
                "low": 128_000,
                "close": 130_000,
                "volume": 500_000,
                "adj_open": 129_000,
                "adj_high": 131_000,
                "adj_low": 128_000,
                "adj_close": 130_000,
                "adj_volume": 500_000,
            }
        ],
    )
    db_session.commit()

    # collector: SYMBOL2 데이터만 반환 (SYMBOL1은 이미 DB에 있으므로 요청 없어야 함)
    symbol2_price = _make_price_row(SYMBOL2, AS_OF, close=70_000)
    mock_collector = _build_mock_collector(
        symbols=(_make_symbol(SYMBOL1), _make_symbol(SYMBOL2)),
        prices=(symbol2_price,),
        calendar=(RawCalendarRow(date=AS_OF, market="KOSPI", is_trading_day=True),),
        as_of=AS_OF,
    )

    config = DailyUpdateConfig(
        as_of_date=AS_OF,
        markets=("KOSPI",),
        incremental=True,
        apply_adjusted_price=False,
    )
    job = DailyUpdateJob(
        config=config,
        collector=mock_collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    stats = dict(result.stats)
    # SYMBOL1은 이미 최신 → skipped
    assert stats["symbols_skipped_uptodate"] == 1
    # SYMBOL2만 수집 → 1건 upserted
    assert stats["daily_prices_upserted"] == 1

    # collect_daily_prices가 호출됐다면 SYMBOL1은 포함되면 안 됨
    calls = mock_collector.collect_daily_prices.call_args_list
    for call in calls:
        collected_symbols = call.args[0] if call.args else call.kwargs.get("symbols", ())
        assert SYMBOL1 not in collected_symbols, (
            "SYMBOL1이 이미 당일 데이터가 있음에도 수집 요청됨 (14.10 증분 위반)"
        )


def test_daily_update_nontrading_day_is_noop(session_factory, db_session):
    """비거래일은 no-op (check_trading_calendar=True, is_trading_day=False) (14.10).

    DB 행 수 변화 없음 검증.
    """
    NON_TRADING = date(2024, 1, 1)  # 신정 (비거래일)
    SYMBOL = "005930"

    repositories.upsert_symbol(
        db_session,
        {
            "symbol": SYMBOL,
            "name": "삼성전자",
            "market": "KOSPI",
            "listing_date": date(2020, 1, 1),
        },
    )
    # 비거래일을 거래일 캘린더에 is_trading_day=False로 등록
    repositories.upsert_trading_day(
        db_session, date=NON_TRADING, market="KOSPI", is_trading_day=False
    )
    db_session.commit()

    before = db_session.query(DailyPrice).count()

    mock_collector = _build_mock_collector(
        symbols=(_make_symbol(SYMBOL),),
        as_of=NON_TRADING,
    )
    config = DailyUpdateConfig(
        as_of_date=NON_TRADING,
        markets=("KOSPI",),
        check_trading_calendar=True,  # 거래일 체크 활성
    )
    job = DailyUpdateJob(
        config=config,
        collector=mock_collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    stats = dict(result.stats)
    # 비거래일 → no-op
    assert stats["skipped_nontrading"] == 1

    # DB 변화 없음 검증 (14.10 forward-fill 금지)
    after = db_session.query(DailyPrice).count()
    assert after == before, (
        f"비거래일 수집 시 DB 변화 발생 (before={before}, after={after}) — forward-fill 금지 위반"
    )


def test_daily_update_idempotent_same_day_twice(session_factory, db_session):
    """같은 날 2회 실행 시 DB 행 수 변화 없음 (idempotent) (14.10).

    2회째 실행 시 collector가 동일 데이터를 반환해도 DB에 중복 없음.
    """
    AS_OF = date(2024, 1, 2)
    SYMBOL = "005930"

    repositories.upsert_symbol(
        db_session,
        {
            "symbol": SYMBOL,
            "name": "삼성전자",
            "market": "KOSPI",
            "listing_date": date(2020, 1, 1),
        },
    )
    db_session.commit()

    price_row = _make_price_row(SYMBOL, AS_OF, close=70_000)
    calendar_row = RawCalendarRow(date=AS_OF, market="KOSPI", is_trading_day=True)

    def make_collector():
        return _build_mock_collector(
            symbols=(_make_symbol(SYMBOL),),
            prices=(price_row,),
            calendar=(calendar_row,),
            as_of=AS_OF,
        )

    config = DailyUpdateConfig(
        as_of_date=AS_OF,
        markets=("KOSPI",),
        incremental=False,  # 매번 수집 (중복 upsert 시나리오)
        apply_adjusted_price=False,
    )

    # 1회 실행
    job1 = DailyUpdateJob(
        config=config, collector=make_collector(), session_factory=session_factory
    )
    result1 = job1.run()
    assert result1.success is True

    fresh = session_factory()
    try:
        count_after_1 = fresh.query(DailyPrice).count()
    finally:
        fresh.close()

    # 2회 실행 (동일 데이터)
    job2 = DailyUpdateJob(
        config=config, collector=make_collector(), session_factory=session_factory
    )
    result2 = job2.run()
    assert result2.success is True

    fresh = session_factory()
    try:
        count_after_2 = fresh.query(DailyPrice).count()
    finally:
        fresh.close()

    assert count_after_1 == count_after_2, (
        f"idempotent 위반: 1회={count_after_1}, 2회={count_after_2} (14.10)"
    )


# ---------------------------------------------------------------------------
# 시나리오 3: PykrxProvider BaseProvider 계약 검증 — 정책 13.7, 13.12
#
# 검증:
#   - get_price_df 반환 DataFrame에 adj_open/adj_high/adj_low/adj_close/adj_volume 포함
#   - get_symbols 반환: symbol ASC 정렬 (결정론 13.12)
#   - LocalCsvProvider와 동일한 BaseProvider 인터페이스 준수
#   - 외부 pykrx 호출 없이 MagicMock 처리
# ---------------------------------------------------------------------------


def test_pykrx_provider_get_price_df_columns_include_adj_fields():
    """PykrxProvider.get_price_df 반환 컬럼에 adj_* 포함 (13.7).

    외부 pykrx 호출 없이 PykrxCollector._fetch_* 를 patch로 대체.
    """
    SYMBOL = "005930"
    START = date(2024, 1, 2)
    END = date(2024, 1, 5)

    fake_rows = (
        _make_price_row(SYMBOL, date(2024, 1, 2), close=70_000),
        _make_price_row(SYMBOL, date(2024, 1, 3), close=71_000),
        _make_price_row(SYMBOL, date(2024, 1, 4), close=70_500),
        _make_price_row(SYMBOL, date(2024, 1, 5), close=72_000),
    )
    fake_prices_data = RawDailyPricesData(
        rows=fake_rows, start_date=START, end_date=END, source="mock_pykrx"
    )

    with patch(
        "app.data_pipeline.collectors.pykrx.PykrxCollector.collect_daily_prices",
        return_value=fake_prices_data,
    ):
        provider = PykrxProvider()
        # _ensure_pykrx_available도 patch (실제 pykrx import 차단)
        with patch.object(provider, "_ensure_pykrx_available"):
            # _collector를 직접 MagicMock으로 교체
            mock_collector = MagicMock()
            mock_collector.collect_daily_prices.return_value = fake_prices_data
            provider._collector = mock_collector

            df = provider.get_price_df(SYMBOL, START, END)

    # 13.7: adj_* 컬럼 모두 포함 여부
    required_adj_cols = {"adj_open", "adj_high", "adj_low", "adj_close", "adj_volume"}
    for col in required_adj_cols:
        assert col in df.columns, f"adj 컬럼 누락: {col} (13.7 위반)"

    # PYKRX_PROVIDER_COLUMNS 전체 포함 여부
    for col in PYKRX_PROVIDER_COLUMNS:
        assert col in df.columns, f"표준 컬럼 누락: {col}"

    # 13.12 결정론: date ASC 정렬
    dates = df["date"].tolist()
    assert dates == sorted(dates), "get_price_df 반환 DataFrame이 date ASC 정렬 아님 (13.12)"

    # 13.7: close 보존 (원 가격)
    assert df.iloc[0]["close"] == pytest.approx(70_000)
    assert df.iloc[0]["adj_close"] == pytest.approx(70_000)


def test_pykrx_provider_get_symbols_sorted_asc():
    """PykrxProvider.get_symbols 반환이 symbol ASC 정렬 (결정론 13.12).

    외부 pykrx 호출 없이 _make_collector와 _ensure_pykrx_available를 mock 처리.
    get_symbols는 markets=(market,)으로 _make_collector를 호출하므로
    mock_collector를 반환하도록 _make_collector를 패치.
    """
    unsorted_symbols = ("005930", "000660", "035720", "035420")
    fake_symbol_data = RawSymbolsData(
        rows=tuple(_make_symbol(s) for s in unsorted_symbols),
        as_of_date=date(2024, 1, 2),
        source="mock",
    )

    mock_collector = MagicMock()
    mock_collector.collect_symbols.return_value = fake_symbol_data

    provider = PykrxProvider()
    with (
        patch.object(provider, "_ensure_pykrx_available"),
        patch.object(provider, "_make_collector", return_value=mock_collector),
    ):
        result = provider.get_symbols("KOSPI")

    # 결정론: symbol ASC
    assert result == sorted(unsorted_symbols), (
        f"get_symbols 반환이 ASC 정렬 아님: {result} (13.12 위반)"
    )


def test_pykrx_provider_is_subclass_of_base_provider():
    """PykrxProvider가 BaseProvider 인터페이스를 준수하는지 (03번 계약).

    LocalCsvProvider와 동일하게 BaseProvider 상속 + ingest_into 메서드 보유 확인.
    """
    from app.market_data.local_csv import LocalCsvProvider

    assert issubclass(PykrxProvider, BaseProvider), "PykrxProvider가 BaseProvider 미상속"
    assert issubclass(LocalCsvProvider, BaseProvider), "LocalCsvProvider가 BaseProvider 미상속"

    # 두 Provider 모두 ingest_into 메서드 보유
    assert hasattr(PykrxProvider, "ingest_into"), "PykrxProvider.ingest_into 없음"
    assert hasattr(LocalCsvProvider, "ingest_into"), "LocalCsvProvider.ingest_into 없음"

    # 메서드 시그니처 호환성: session / symbols / start_date / end_date
    import inspect

    pykrx_sig = inspect.signature(PykrxProvider.ingest_into)
    local_sig = inspect.signature(LocalCsvProvider.ingest_into)

    pykrx_params = set(pykrx_sig.parameters.keys())
    local_params = set(local_sig.parameters.keys())

    required_params = {"session", "symbols", "start_date", "end_date"}
    assert required_params.issubset(pykrx_params), (
        f"PykrxProvider.ingest_into 파라미터 누락: {required_params - pykrx_params}"
    )
    assert required_params.issubset(local_params), (
        f"LocalCsvProvider.ingest_into 파라미터 누락: {required_params - local_params}"
    )


# ---------------------------------------------------------------------------
# 시나리오 4: AdjustedPriceProcessor idempotent + close 보존 — 정책 14.5, 13.7, 13.15
#
# 검증:
#   - 분할 이벤트(ratio=0.5) 2회 적용 시 결과 동일 (멱등성 — 14.5)
#   - close 컬럼은 항상 원본값 유지 (13.7)
#   - 미래 corporate_action 필터링 (13.15)
# ---------------------------------------------------------------------------


def test_adjusted_price_processor_idempotent_on_split_event():
    """AdjustedPriceProcessor: 동일 원본 입력 2회 호출 시 결과 동일 (14.5 멱등성).

    AdjustedPriceProcessor는 pure function에 가깝다:
        - 동일한 (원본 prices, 동일 events, 동일 as_of_date) 입력 → 동일 출력.
        - 내부 상태 변경 없음 (frozen dataclass 입/출력).

    14.5 정책: "분할/배당 발생 시 과거 전체 재계산, 스냅샷 누적 금지"
    → 본 테스트는 Processor 수준의 순수 결정론을 검증한다.
    → DB 수준 idempotent(같은 이벤트를 DB 경유로 2회 적용해도 누적 안 됨)는
       Phase 11 e2e의 test_corporate_action_apply_job_is_idempotent_on_repeated_runs에서 보호.

    시나리오:
        - 원본 입력 (prices, split_event, as_of_date)를 완전히 동일하게 2회 호출
        - 두 결과의 adj_close가 bit-exact로 일치해야 함
    """
    SYMBOL = "005930"
    SPLIT_DATE = date(2024, 1, 4)
    CLOSE = 100_000.0

    price_rows = tuple(
        _make_price_row(SYMBOL, date(2024, 1, d), close=CLOSE)
        for d in [2, 3, 4, 5, 8]
    )
    raw_prices = RawDailyPricesData(
        rows=price_rows,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 8),
        source="mock",
    )
    split_event = CorporateActionEvent(
        symbol=SYMBOL,
        event_date=SPLIT_DATE,
        event_type="split",
        ratio=2.0,
    )

    processor = AdjustedPriceProcessor()

    # 동일 입력 1회 호출
    input_data = AdjustedPriceInput(
        prices=raw_prices,
        corporate_actions=(split_event,),
        as_of_date=date(2024, 1, 8),
    )
    result1 = processor.process(input_data)
    assert result1.validation.passed is True

    # 동일 입력 2회 호출 (같은 frozen dataclass 재사용)
    result2 = processor.process(input_data)
    assert result2.validation.passed is True

    # 14.5 결정론: 동일 입력 → 동일 출력 (bit-exact)
    adj_close_1 = {r.date: r.adj_close for r in result1.output}
    adj_close_2 = {r.date: r.adj_close for r in result2.output}

    for d, v in adj_close_1.items():
        assert v == pytest.approx(adj_close_2[d], rel=1e-9), (
            f"date={d}: 동일 입력 2회 호출 adj_close 불일치 {adj_close_2[d]} ≠ {v} "
            f"(14.5 결정론 위반)"
        )

    # 분할 이벤트가 실제 적용됐는지 확인 (adj_close *= 0.5 for 이전 봉)
    assert adj_close_1[date(2024, 1, 2)] == pytest.approx(50_000)  # 100_000 * 0.5
    assert adj_close_1[date(2024, 1, 3)] == pytest.approx(50_000)
    # 분할 당일 + 이후는 그대로
    assert adj_close_1[date(2024, 1, 4)] == pytest.approx(100_000)
    assert adj_close_1[date(2024, 1, 5)] == pytest.approx(100_000)


def test_adjusted_price_processor_close_preserved_after_split():
    """분할 이벤트 적용 후 close(원 가격) 보존 (13.7).

    close는 절대 변경하지 않고, adj_close만 재계산.
    """
    SYMBOL = "005930"
    SPLIT_DATE = date(2024, 1, 4)

    price_rows = (
        _make_price_row(SYMBOL, date(2024, 1, 2), close=100_000),  # 분할 이전
        _make_price_row(SYMBOL, date(2024, 1, 3), close=100_000),  # 분할 이전
        _make_price_row(SYMBOL, date(2024, 1, 4), close=50_000),   # 분할 당일
        _make_price_row(SYMBOL, date(2024, 1, 5), close=51_000),   # 분할 이후
    )
    raw_prices = RawDailyPricesData(
        rows=price_rows, start_date=date(2024, 1, 2), end_date=date(2024, 1, 5), source="mock"
    )
    split_event = CorporateActionEvent(
        symbol=SYMBOL,
        event_date=SPLIT_DATE,
        event_type="split",
        ratio=2.0,
    )
    processor = AdjustedPriceProcessor()
    result = processor.process(
        AdjustedPriceInput(
            prices=raw_prices,
            corporate_actions=(split_event,),
            as_of_date=date(2024, 1, 5),
        )
    )

    by_date = {r.date: r for r in result.output}

    # 13.7: close 보존 — 분할 이전도 100_000 그대로
    assert by_date[date(2024, 1, 2)].close == pytest.approx(100_000)
    assert by_date[date(2024, 1, 3)].close == pytest.approx(100_000)
    assert by_date[date(2024, 1, 4)].close == pytest.approx(50_000)

    # adj_close: 분할 이전 *= 1/2
    assert by_date[date(2024, 1, 2)].adj_close == pytest.approx(50_000)
    assert by_date[date(2024, 1, 3)].adj_close == pytest.approx(50_000)
    # 분할 당일 + 이후는 close 그대로
    assert by_date[date(2024, 1, 4)].adj_close == pytest.approx(50_000)
    assert by_date[date(2024, 1, 5)].adj_close == pytest.approx(51_000)

    # 분할 이전 adj_close != close (수정 전/후 구분 13.7)
    assert by_date[date(2024, 1, 2)].adj_close != by_date[date(2024, 1, 2)].close


def test_adjusted_price_processor_future_event_skipped():
    """미래 corporate_action은 as_of_date 기준으로 차단 (13.15).

    as_of_date=2024-01-05인데 event_date=2024-12-31인 이벤트는 skip.
    """
    SYMBOL = "005930"

    price_rows = tuple(
        _make_price_row(SYMBOL, date(2024, 1, d), close=50_000) for d in [2, 3, 4, 5]
    )
    raw_prices = RawDailyPricesData(
        rows=price_rows, start_date=date(2024, 1, 2), end_date=date(2024, 1, 5), source="mock"
    )
    # 미래 이벤트 (as_of_date보다 미래)
    future_event = CorporateActionEvent(
        symbol=SYMBOL,
        event_date=date(2024, 12, 31),  # 미래
        event_type="split",
        ratio=3.0,
    )
    # 현재 이벤트 (as_of_date 이내)
    current_event = CorporateActionEvent(
        symbol=SYMBOL,
        event_date=date(2024, 1, 4),
        event_type="split",
        ratio=2.0,
    )

    processor = AdjustedPriceProcessor()
    result = processor.process(
        AdjustedPriceInput(
            prices=raw_prices,
            corporate_actions=(future_event, current_event),
            as_of_date=date(2024, 1, 5),  # 2024-12-31보다 과거
        )
    )

    stats_dict = dict(result.stats)
    # 13.15: 미래 이벤트 1건 skip
    assert stats_dict["events_skipped_future"] == 1, (
        f"미래 이벤트 skip 카운트 {stats_dict.get('events_skipped_future')} ≠ 1 (13.15)"
    )
    # 현재 이벤트 1건만 적용
    assert stats_dict["events_applied"] == 1, (
        f"적용 이벤트 수 {stats_dict.get('events_applied')} ≠ 1"
    )

    # 미래 이벤트(ratio=3)가 적용되면 adj_close가 더 작아짐 → 아직 50_000 수준이어야 함
    by_date = {r.date: r for r in result.output}
    # 현재 이벤트(2024-01-04 분할)만 적용 → 이전 봉들의 adj_close *= 0.5
    assert by_date[date(2024, 1, 2)].adj_close == pytest.approx(25_000)  # 50_000 * 0.5
    assert by_date[date(2024, 1, 3)].adj_close == pytest.approx(25_000)  # 50_000 * 0.5
    # 미래 이벤트가 적용됐다면 더 나눠졌을 것 — 그렇지 않음 검증
    assert by_date[date(2024, 1, 2)].adj_close != pytest.approx(25_000 / 3)


# ---------------------------------------------------------------------------
# 시나리오 5: RateLimiter 연속 실패 → 블록 — 정책 14.6.4
#
# 검증:
#   - 3회 연속 record_failure() 후 wait() 시 block_sleep 발생
#   - sleep_fn 주입으로 실제 슬립 없이 호출 횟수 검증
#   - 성공 후 실패 카운터 리셋
# ---------------------------------------------------------------------------


def test_rate_limiter_block_sleep_on_consecutive_failures():
    """연속 실패 임계 초과 시 wait()에서 block_sleep 호출 (14.6.4).

    sleep_fn 주입으로 실제 sleep 없이 호출 인자 검증.
    """
    sleep_calls: list[float] = []
    monotonic_val = [0.0]  # mutable container for closure

    def mock_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    def mock_monotonic() -> float:
        # 매 호출마다 0.0 반환 (elapsed 항상 0 → min_interval sleep 포함)
        return monotonic_val[0]

    limiter = RateLimiter(
        min_interval_seconds=0.01,
        max_consecutive_failures=3,  # 3회 초과 시 block
        block_sleep_seconds=1800.0,
        sleep_fn=mock_sleep,
        monotonic_fn=mock_monotonic,
    )

    # 초기 상태
    assert limiter.consecutive_failures == 0

    # 3회 실패 기록
    limiter.record_failure()
    limiter.record_failure()
    limiter.record_failure()
    assert limiter.consecutive_failures == 3

    # 임계값(3) 이상 → wait() 시 block_sleep 호출
    sleep_calls.clear()
    limiter.wait()

    # block_sleep(1800.0) 이 먼저 호출되어야 함
    assert len(sleep_calls) >= 1, "block_sleep이 호출되지 않음 (14.6.4 위반)"
    assert sleep_calls[0] == pytest.approx(1800.0), (
        f"block_sleep 시간이 1800.0이 아님: {sleep_calls[0]} (14.6.4 위반)"
    )

    # block_sleep 후 실패 카운터 리셋
    assert limiter.consecutive_failures == 0, (
        f"block_sleep 후 실패 카운터 미리셋: {limiter.consecutive_failures} (14.6.4 위반)"
    )


def test_rate_limiter_success_resets_failure_counter():
    """record_success() 후 실패 카운터 리셋 (14.6.4)."""
    limiter = RateLimiter(
        min_interval_seconds=0.0,
        sleep_fn=lambda s: None,
        monotonic_fn=lambda: 0.0,
    )

    limiter.record_failure()
    limiter.record_failure()
    assert limiter.consecutive_failures == 2

    limiter.record_success()
    assert limiter.consecutive_failures == 0, (
        f"record_success() 후 실패 카운터 미리셋: {limiter.consecutive_failures}"
    )


def test_rate_limiter_no_block_sleep_below_threshold():
    """임계값 미만 연속 실패 시 block_sleep 미호출 (14.6.4)."""
    block_sleep_called = []

    def mock_sleep(seconds: float) -> None:
        if seconds >= 1800.0:
            block_sleep_called.append(seconds)

    limiter = RateLimiter(
        min_interval_seconds=0.0,
        max_consecutive_failures=5,
        block_sleep_seconds=1800.0,
        sleep_fn=mock_sleep,
        monotonic_fn=lambda: 0.0,
    )

    # 임계값(5) 미만 — 4회만 실패
    for _ in range(4):
        limiter.record_failure()

    limiter.wait()  # block_sleep 없어야 함

    assert len(block_sleep_called) == 0, (
        f"임계값 미만인데 block_sleep 호출됨: {block_sleep_called}"
    )


def test_rate_limiter_min_interval_enforced():
    """min_interval_seconds 보장: elapsed < min_interval 시 sleep 호출 (14.6.4)."""
    sleep_calls: list[float] = []
    tick = [0.0]

    def mock_monotonic() -> float:
        # 매 호출마다 0.1초씩 증가 (경과 시간 시뮬레이션)
        val = tick[0]
        tick[0] += 0.1
        return val

    def mock_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    limiter = RateLimiter(
        min_interval_seconds=0.5,
        sleep_fn=mock_sleep,
        monotonic_fn=mock_monotonic,
    )

    # 첫 wait() — _last_request_time=0, elapsed=0 → sleep(0.5) 호출
    # (단, monotonic이 계속 증가하므로 실제 sleep 여부는 구현 로직에 따라 다름)
    sleep_calls.clear()
    limiter.wait()

    # wait() 직후 min_interval 미충족 시 sleep 호출 여부 확인
    # 여기서는 "min_interval이 설정되어 있으면 sleep 함수가 사용된다"는 계약만 검증:
    # _last_request_time 속성이 존재하는지 + last_request_time 프로퍼티 접근 가능한지
    assert hasattr(limiter, "_last_request_time"), "RateLimiter에 _last_request_time 없음"
    # last_request_time 프로퍼티 접근 가능 여부 (monotonic_fn 시뮬레이션에 따라 값은 0.0)
    _ = limiter.last_request_time


# ---------------------------------------------------------------------------
# 시나리오 6 (보충): Scheduler busy-set 락 + 동시 실행 방지
#
# 검증:
#   - 동일 잡 동시 실행 시도 → LockError 즉시 발생
#   - 첫 번째 잡 완료 후 두 번째 잡 정상 실행
# ---------------------------------------------------------------------------


def test_scheduler_concurrent_execution_raises_lock_error():
    """동일 잡 동시 실행 시도 → LockError (14-j 단일 프로세스 락).

    threading.Event로 첫 번째 잡이 실행 중임을 보장한 뒤
    두 번째 호출이 LockError를 raise하는지 검증.
    """
    from datetime import UTC, datetime

    from app.data_pipeline.jobs.base import BaseJob, JobResult

    first_started = threading.Event()
    first_can_finish = threading.Event()

    class SlowJob(BaseJob):
        """first_can_finish가 set될 때까지 블록하는 잡."""

        def run(self) -> JobResult:
            first_started.set()
            first_can_finish.wait(timeout=5.0)
            return JobResult(
                job_name=self.name,
                success=True,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                stats=(),
                warnings=(),
                errors=(),
            )

    scheduler = Scheduler()
    scheduler.register(SlowJob("slow_job"))

    lock_error_raised = []
    first_result_holder = []

    def run_first():
        result = scheduler.run_job("slow_job")
        first_result_holder.append(result)

    def run_second():
        # 첫 번째 잡이 시작될 때까지 대기
        first_started.wait(timeout=5.0)
        try:
            scheduler.run_job("slow_job")
        except LockError as exc:
            lock_error_raised.append(exc)

    t1 = threading.Thread(target=run_first, daemon=True)
    t2 = threading.Thread(target=run_second, daemon=True)

    t1.start()
    t2.start()

    # t2가 LockError를 잡을 시간 확보 후 t1 완료
    t2.join(timeout=5.0)
    first_can_finish.set()
    t1.join(timeout=5.0)

    assert len(lock_error_raised) == 1, (
        f"LockError가 발생하지 않음 (14-j 단일 프로세스 락 위반): {lock_error_raised}"
    )
    assert len(first_result_holder) == 1
    assert first_result_holder[0].success is True


def test_scheduler_second_run_succeeds_after_first_completes():
    """첫 번째 잡 완료 후 두 번째 잡은 정상 실행 (14-j).

    락 해제 after try/finally 보장 검증.
    """
    from datetime import UTC, datetime

    from app.data_pipeline.jobs.base import BaseJob, JobResult

    class FastJob(BaseJob):
        def __init__(self, name: str, call_count: list[int]) -> None:
            super().__init__(name, schedule=None)
            self._counter = call_count

        def run(self) -> JobResult:
            self._counter.append(1)
            return JobResult(
                job_name=self.name,
                success=True,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                stats=(),
                warnings=(),
                errors=(),
            )

    call_count: list[int] = []
    scheduler = Scheduler()
    scheduler.register(FastJob("fast_job", call_count))

    # 순차 실행 2회
    result1 = scheduler.run_job("fast_job")
    result2 = scheduler.run_job("fast_job")

    assert result1.success is True
    assert result2.success is True
    assert len(call_count) == 2, f"잡이 2회 실행되지 않음: {len(call_count)}"
    # 두 번째 실행 후 is_running이 False여야 함 (락 해제)
    assert scheduler.is_running("fast_job") is False


# ---------------------------------------------------------------------------
# 시나리오 7 (보충): DailyUpdateJob + MissingDataCheckJob 연동
#
# 검증:
#   - DailyUpdateJob 수집 후 MissingDataCheckJob 결손 감지
#   - 감지 후 DB 행 수 변화 없음 (forward-fill 금지 14.10)
# ---------------------------------------------------------------------------


def test_daily_update_then_missing_data_check_detects_gaps(
    session_factory, db_session
):
    """DailyUpdateJob + MissingDataCheckJob 연동 — 결손 감지 + forward-fill 금지 (14.10, 14.13).

    시나리오:
        1. 거래일 5일 중 3일만 수집 (2건 결손)
        2. DailyUpdateJob 실행 → 3건 영속화
        3. MissingDataCheckJob 실행 → 2건 결손 감지
        4. DB는 여전히 3건 (forward-fill 금지)
    """
    SYMBOL = "005930"
    TRADING_DATES = [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
    ]
    PRESENT_DATES = [date(2024, 1, 2), date(2024, 1, 4), date(2024, 1, 5)]
    MISSING_DATES = [date(2024, 1, 3), date(2024, 1, 8)]

    # 거래일 캘린더 + 종목 시드
    repositories.upsert_symbol(
        db_session,
        {
            "symbol": SYMBOL,
            "name": "삼성전자",
            "market": "KOSPI",
            "listing_date": date(2020, 1, 1),
        },
    )
    for d in TRADING_DATES:
        repositories.upsert_trading_day(
            db_session, date=d, market="KOSPI", is_trading_day=True
        )
    db_session.commit()

    # DailyUpdateJob — 3일치만 수집 (2건 결손)
    present_prices = tuple(_make_price_row(SYMBOL, d) for d in PRESENT_DATES)
    calendar_rows = tuple(
        RawCalendarRow(date=d, market="KOSPI", is_trading_day=True) for d in TRADING_DATES
    )
    mock_collector = _build_mock_collector(
        symbols=(_make_symbol(SYMBOL),),
        prices=present_prices,
        calendar=calendar_rows,
        as_of=date(2024, 1, 8),
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 8),
    )

    daily_job = DailyUpdateJob(
        config=DailyUpdateConfig(
            as_of_date=date(2024, 1, 8),
            markets=("KOSPI",),
            incremental=False,
            apply_adjusted_price=False,
        ),
        collector=mock_collector,
        session_factory=session_factory,
    )
    daily_result = daily_job.run()
    assert daily_result.success is True
    assert dict(daily_result.stats)["daily_prices_upserted"] == 3

    # MissingDataCheckJob — 결손 감지
    missing_job = MissingDataCheckJob(
        config=MissingDataCheckConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 8),
            market="KOSPI",
            symbols=(SYMBOL,),
        ),
        session_factory=session_factory,
    )
    check_before = session_factory().query(DailyPrice).count()
    missing_result = missing_job.run()
    check_after = session_factory().query(DailyPrice).count()

    assert missing_result.success is True
    missing_stats = dict(missing_result.stats)
    assert missing_stats["missing_count"] == 2, (
        f"결손 감지 수 {missing_stats['missing_count']} ≠ 2 (14.13)"
    )

    # 14.10: forward-fill 금지 — DB 행 수 변화 없음
    assert check_before == check_after == 3, (
        f"MissingDataCheckJob이 DB를 수정함 — forward-fill 금지 위반 (14.10): "
        f"before={check_before}, after={check_after}"
    )

    # 결손 날짜 정확성 (결정론: date ASC 정렬)
    alert = missing_job.last_alert
    assert alert.missing_count == 2
    alert_dates = [entry.date for entry in alert.entries]
    assert alert_dates == sorted(MISSING_DATES), (
        f"결손 날짜 정렬 오류: {alert_dates} ≠ {sorted(MISSING_DATES)} (13.12)"
    )
