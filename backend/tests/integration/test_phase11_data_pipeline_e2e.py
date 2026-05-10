"""Phase 11 e2e 통합 시나리오 — data_pipeline 본체 (collector/processor/jobs/scheduler).

Phase 11 step 024~028이 도입한 5개 핵심 영역의 cross-component contract를 보호한다.
각 step의 단위 테스트(`backend/tests/data_pipeline/`)는 자체 영역만 검증하므로,
본 통합 테스트는 5개 영역이 동일 SQLAlchemy Session 위에서 협업할 때
**결정론 + look-ahead 차단 + idempotent + forward-fill 금지**를 e2e로 회귀 보호한다.

검증 매핑 (정확성 정책 13.x / 14.x):
    - 13.7  (수정주가 정합 — close 보존, adj_*만 재계산)        → 시나리오 1·3
    - 13.12 (결정론 — frozen dataclass + sorted)                → 시나리오 1·4
    - 13.13 (생존편향 — universe_history 폐지 종목 보존)         → 시나리오 4
    - 13.15 (look-ahead — 미래 corporate_action 차단)            → 시나리오 1·3
    - 14.5  (분할/배당 발생 시 과거 전체 재계산, 누적 금지)        → 시나리오 3 (idempotent)
    - 14.10 (forward-fill 금지)                                  → 시나리오 5
    - 14.13 (데이터 결손 알림 — MissingDataCheckJob 감지만)        → 시나리오 5
    - CLAUDE.md #8 (결정론 보장)                                  → 모든 시나리오

본 모듈은 의도적으로 Phase 11 단위 테스트가 다루지 않는 *e2e 라운드트립*만 다룬다:
    - 단위 테스트: in-memory dataclass / mock collector / 단일 컴포넌트
    - 본 e2e:    PykrxCollector(mock) → AdjustedPriceProcessor → repositories → DB ORM
                 → 후속 잡 재호출 시 idempotent 검증

외부 fetch: 0건 (collector는 모두 MagicMock 또는 dataclass 직주입).
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
from app.data_pipeline.jobs.corporate_action_apply import (
    CorporateActionApplyConfig,
    CorporateActionApplyJob,
)
from app.data_pipeline.jobs.daily_update import (
    DailyUpdateConfig,
    DailyUpdateJob,
)
from app.data_pipeline.jobs.missing_data_check import (
    MissingDataCheckConfig,
    MissingDataCheckJob,
)
from app.data_pipeline.jobs.universe_snapshot import (
    UniverseSnapshotConfig,
    UniverseSnapshotJob,
    compute_config_hash,
)
from app.data_pipeline.processors.adjusted_price import (
    AdjustedPriceInput,
    AdjustedPriceProcessor,
    CorporateActionEvent,
)
from app.db.session import (
    create_db_engine,
    drop_db,
    init_db,
    make_session_factory,
)
from app.market_data import repositories
from app.market_data.universe import SELECTION_METHOD_ALL
from app.models.daily_price import DailyPrice
from app.models.universe_history import UniverseHistory

# ---------------------------------------------------------------------------
# 공통 fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db_engine():
    """in-memory SQLite + 전 테이블 생성."""
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    try:
        yield engine
    finally:
        drop_db(engine)
        engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    """잡이 호출할 때마다 새 세션을 반환하는 callable.

    잡 내부 _session_scope가 세션을 close()하므로 fixture가 매번 새 세션을 만든다.
    """
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
# 헬퍼 — Phase 11 단위 테스트와 동일 시그니처
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


def _make_price(
    code: str,
    d: date,
    close: float = 70_000.0,
    *,
    adj_close: float | None = None,
) -> RawDailyPriceRow:
    """일봉 1건. adj_close 미지정 시 close와 동일 (13.7 — close 보존).

    025 PykrxCollector의 출력 형태: 최초 수집 시 adj_* == 원 가격
    (factor 적용 전). 026 AdjustedPriceProcessor가 corporate_actions를 적용해
    adj_*만 갱신.
    """
    if adj_close is None:
        adj_close = close
    # close 보존 정책에 따라 high/low/open도 비슷한 형태로 채움
    return RawDailyPriceRow(
        symbol=code,
        date=d,
        open=close - 100,
        high=close + 200,
        low=close - 200,
        close=close,
        volume=1_000_000,
        adj_open=adj_close - 100 * (adj_close / close),
        adj_high=adj_close + 200 * (adj_close / close),
        adj_low=adj_close - 200 * (adj_close / close),
        adj_close=adj_close,
        adj_volume=1_000_000 * (close / adj_close) if adj_close > 0 else 1_000_000,
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
    """025 PykrxCollector 인터페이스를 mock으로 흉내낸 BaseCollector.

    DailyUpdateJob은 collect_daily_prices(symbols, start, end)를 호출하므로,
    start/end 인자는 fixture에서 제공한 값을 그대로 echo한다.
    """
    mock = MagicMock(spec=BaseCollector)
    mock.collect_symbols.return_value = RawSymbolsData(
        rows=symbols, as_of_date=as_of, source="mock_pykrx"
    )
    mock.collect_daily_prices.return_value = RawDailyPricesData(
        rows=prices,
        start_date=start_date or as_of,
        end_date=end_date or as_of,
        source="mock_pykrx",
    )
    mock.collect_trading_calendar.return_value = RawCalendarData(
        rows=calendar,
        start_date=start_date or as_of,
        end_date=end_date or as_of,
        market="KOSPI",
        source="mock_pykrx",
    )
    return mock


# ---------------------------------------------------------------------------
# 시나리오 1: PykrxCollector(mock) → AdjustedPriceProcessor → repositories 라운드트립
# ---------------------------------------------------------------------------


def test_collector_processor_repositories_roundtrip_split_event(
    db_session, session_factory
):
    """025 collector → 026 processor → 016 repositories 전체 라운드트립.

    시나리오:
        1. 025 mock collector가 (2024-01-02 ~ 2024-01-08) 7봉 + 분할 이전 가격 시계열
           (2024-01-04 액면분할 1:2)을 반환
        2. 026 AdjustedPriceProcessor가 분할 이전(01-02, 01-03)의 adj_close에
           1/2 factor 적용
        3. 016 repositories.bulk_upsert_daily_prices로 영속화
        4. 016 repositories.get_price_range로 다시 조회

    검증:
        - 13.7: close (원 가격) 보존 — factor 적용 안 함
        - 13.7: adj_close — 분할 이전만 1/2 적용 (분할일 당일 + 이후 보존)
        - 13.15: 미래 이벤트 차단 (as_of_date보다 미래 event_date는 무시)
        - CLAUDE.md #8: (symbol ASC, date ASC) 결정론
    """
    SYMBOL = "005930"
    SPLIT_DATE = date(2024, 1, 4)

    # daily_prices.symbol FK 만족을 위해 symbols 시드
    repositories.upsert_symbol(
        db_session,
        {
            "symbol": SYMBOL, "name": "삼성전자",
            "market": "KOSPI", "listing_date": date(2020, 1, 1),
        },
    )
    db_session.commit()

    # 분할 이전: close=100_000, 분할 당일+이후: close=50_000 (실제 시장 가격 흐름)
    pre_split_prices = [
        _make_price(SYMBOL, date(2024, 1, 2), close=100_000),
        _make_price(SYMBOL, date(2024, 1, 3), close=100_000),
    ]
    post_split_prices = [
        _make_price(SYMBOL, date(2024, 1, 4), close=50_000),
        _make_price(SYMBOL, date(2024, 1, 5), close=51_000),
        _make_price(SYMBOL, date(2024, 1, 8), close=52_000),
    ]
    raw_prices = RawDailyPricesData(
        rows=tuple(pre_split_prices + post_split_prices),
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 8),
        source="mock_pykrx",
    )

    # 026 processor에 전달할 corporate_action — 분할
    events = (
        CorporateActionEvent(
            symbol=SYMBOL,
            event_date=SPLIT_DATE,
            event_type="split",
            ratio=2.0,  # 1주 → 2주
        ),
        # 13.15 검증: 미래 이벤트는 무시되어야 함
        CorporateActionEvent(
            symbol=SYMBOL,
            event_date=date(2024, 12, 31),
            event_type="split",
            ratio=3.0,
        ),
    )

    processor = AdjustedPriceProcessor()
    proc_result = processor.process(
        AdjustedPriceInput(
            prices=raw_prices,
            corporate_actions=events,
            as_of_date=date(2024, 1, 8),  # 미래 이벤트 차단 기준일
        )
    )

    assert proc_result.validation.passed is True
    stats_dict = dict(proc_result.stats)
    assert stats_dict["events_applied"] == 1, "분할 이벤트 1건만 적용 (미래는 skip)"
    assert stats_dict["events_skipped_future"] == 1, "미래 이벤트 1건 skip (13.15)"

    # 016 repositories로 영속화 (rows_to_dicts 변환)
    rows_to_persist = [
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
            "market_cap": r.market_cap,
        }
        for r in proc_result.output
    ]
    upserted = repositories.bulk_upsert_daily_prices(db_session, rows_to_persist)
    db_session.commit()
    assert upserted == 5  # 5봉

    # 016 repositories로 라운드트립 검증
    persisted = repositories.get_price_range(
        db_session, SYMBOL, date(2024, 1, 2), date(2024, 1, 8)
    )
    persisted_by_date = {p.date: p for p in persisted}

    # 13.7: close 보존 (원 가격) — 분할 이전도 100_000 그대로
    assert persisted_by_date[date(2024, 1, 2)].close == 100_000
    assert persisted_by_date[date(2024, 1, 3)].close == 100_000
    assert persisted_by_date[date(2024, 1, 4)].close == 50_000
    # 13.7: adj_close — 분할 이전만 1/2 factor 적용 (50_000)
    assert persisted_by_date[date(2024, 1, 2)].adj_close == pytest.approx(50_000)
    assert persisted_by_date[date(2024, 1, 3)].adj_close == pytest.approx(50_000)
    # 분할 당일 + 이후는 그대로
    assert persisted_by_date[date(2024, 1, 4)].adj_close == pytest.approx(50_000)
    assert persisted_by_date[date(2024, 1, 5)].adj_close == pytest.approx(51_000)
    assert persisted_by_date[date(2024, 1, 8)].adj_close == pytest.approx(52_000)
    # adj_volume — 분할 이전은 2배 (1주가 2주가 됨)
    assert persisted_by_date[date(2024, 1, 2)].adj_volume == pytest.approx(2_000_000)
    # 분할 당일 + 이후는 그대로
    assert persisted_by_date[date(2024, 1, 4)].adj_volume == pytest.approx(1_000_000)


# ---------------------------------------------------------------------------
# 시나리오 2: DailyUpdateJob 전체 흐름 (collector mock → processor → repositories → DB)
# ---------------------------------------------------------------------------


def test_daily_update_job_full_pipeline_persists_all_three_kinds(
    session_factory, db_session
):
    """028 DailyUpdateJob 전체 흐름 — symbols / calendar / daily_prices 모두 영속화.

    검증:
        - 14.6.2 (일일 증분 수집)
        - 14.10 (forward-fill 금지) — collector가 안 준 종목/날짜는 DB에도 row 없음
        - CLAUDE.md #8 (결정론) — symbol ASC 정렬 영속화
    """
    AS_OF = date(2024, 1, 2)
    symbols = (
        _make_symbol("000660"),
        _make_symbol("005930"),
    )
    prices = (
        _make_price("000660", AS_OF, close=130_000),
        _make_price("005930", AS_OF, close=70_000),
    )
    calendar = (RawCalendarRow(date=AS_OF, market="KOSPI", is_trading_day=True),)
    collector = _build_mock_collector(
        symbols=symbols, prices=prices, calendar=calendar, as_of=AS_OF
    )

    job = DailyUpdateJob(
        config=DailyUpdateConfig(as_of_date=AS_OF, markets=("KOSPI",)),
        collector=collector,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    assert result.errors == ()
    stats = dict(result.stats)
    assert stats["symbols_upserted"] == 2
    assert stats["trading_days_upserted"] == 1
    assert stats["daily_prices_upserted"] == 2
    assert stats["events_applied"] == 0  # corporate_actions 비어 있음

    # 새 세션으로 DB 검증 — 잡이 close()한 세션과 분리
    fresh = session_factory()
    try:
        all_prices = (
            fresh.query(DailyPrice).order_by(DailyPrice.symbol).all()
        )
        # 결정론: symbol ASC
        assert [p.symbol for p in all_prices] == ["000660", "005930"]
        # 13.7: adj_close가 NOT NULL이며 close와 일치 (corporate_actions 없으므로 그대로)
        assert all_prices[0].close == 130_000
        assert all_prices[0].adj_close == 130_000
    finally:
        fresh.close()


# ---------------------------------------------------------------------------
# 시나리오 3: CorporateActionApplyJob idempotent (5회 반복 시 누적 적용 안 됨)
# ---------------------------------------------------------------------------


def test_corporate_action_apply_job_is_idempotent_on_repeated_runs(
    session_factory, db_session
):
    """028 CorporateActionApplyJob을 5회 반복해도 adj_*가 누적 적용되지 않는지.

    14.5 / 13.7 핵심 정합:
        - "분할/배당 발생 시 과거 전체 재계산, 스냅샷 누적 금지"
        - 본 잡은 매 호출마다 adj_* = close로 reset 후 재계산 → idempotent

    시나리오:
        1. 종목 1개에 대해 일봉 5건 + 액면분할(1:2) 1건을 시드
        2. CorporateActionApplyJob을 1회 실행 → 분할 이전 adj_close가 1/2로 적용
        3. 같은 잡을 4회 추가 실행
        4. 1회 실행 결과와 5회 실행 결과의 adj_close가 동일한지 (누적 적용 X)
    """
    SYMBOL = "005930"
    SPLIT_DATE = date(2024, 1, 4)

    # 종목 시드
    repositories.upsert_symbol(
        db_session,
        {
            "symbol": SYMBOL,
            "name": "삼성전자",
            "market": "KOSPI",
            "listing_date": date(2020, 1, 1),
        },
    )

    # 일봉 시드 (collector → processor 거치지 않고 직접 — 분할 적용 전 상태)
    rows_seed = [
        {
            "symbol": SYMBOL,
            "date": date(2024, 1, 2),
            "open": 99_000,
            "high": 101_000,
            "low": 98_500,
            "close": 100_000,
            "volume": 1_000_000,
            "adj_open": 99_000,
            "adj_high": 101_000,
            "adj_low": 98_500,
            "adj_close": 100_000,
            "adj_volume": 1_000_000,
        },
        {
            "symbol": SYMBOL,
            "date": date(2024, 1, 3),
            "open": 100_500,
            "high": 102_000,
            "low": 99_500,
            "close": 100_000,
            "volume": 1_000_000,
            "adj_open": 100_500,
            "adj_high": 102_000,
            "adj_low": 99_500,
            "adj_close": 100_000,
            "adj_volume": 1_000_000,
        },
        {
            "symbol": SYMBOL,
            "date": date(2024, 1, 4),
            "open": 49_500,
            "high": 51_000,
            "low": 49_000,
            "close": 50_000,
            "volume": 1_000_000,
            "adj_open": 49_500,
            "adj_high": 51_000,
            "adj_low": 49_000,
            "adj_close": 50_000,
            "adj_volume": 1_000_000,
        },
        {
            "symbol": SYMBOL,
            "date": date(2024, 1, 5),
            "open": 50_500,
            "high": 51_500,
            "low": 50_000,
            "close": 51_000,
            "volume": 1_000_000,
            "adj_open": 50_500,
            "adj_high": 51_500,
            "adj_low": 50_000,
            "adj_close": 51_000,
            "adj_volume": 1_000_000,
        },
        {
            "symbol": SYMBOL,
            "date": date(2024, 1, 8),
            "open": 51_500,
            "high": 52_500,
            "low": 51_000,
            "close": 52_000,
            "volume": 1_000_000,
            "adj_open": 51_500,
            "adj_high": 52_500,
            "adj_low": 51_000,
            "adj_close": 52_000,
            "adj_volume": 1_000_000,
        },
    ]
    repositories.bulk_upsert_daily_prices(db_session, rows_seed)

    # corporate_action 시드 — 1:2 분할
    repositories.upsert_corporate_action(
        db_session,
        {
            "symbol": SYMBOL,
            "event_date": SPLIT_DATE,
            "event_type": "split",
            "ratio": 2.0,
        },
    )
    db_session.commit()

    job = CorporateActionApplyJob(
        config=CorporateActionApplyConfig(
            symbols=(SYMBOL,),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 8),
        ),
        session_factory=session_factory,
    )

    # 1회 실행
    result1 = job.run()
    assert result1.success is True

    # 1회 실행 후 adj_close 캡처
    fresh = session_factory()
    try:
        rows_after_1 = repositories.get_price_range(
            fresh, SYMBOL, date(2024, 1, 2), date(2024, 1, 8)
        )
        adj_close_after_1 = {r.date: r.adj_close for r in rows_after_1}
    finally:
        fresh.close()

    # 14.5: 분할 이전 adj_close == close * (1/2) — 50_000
    assert adj_close_after_1[date(2024, 1, 2)] == pytest.approx(50_000)
    assert adj_close_after_1[date(2024, 1, 3)] == pytest.approx(50_000)
    # 분할 당일 + 이후는 close 그대로
    assert adj_close_after_1[date(2024, 1, 4)] == pytest.approx(50_000)
    assert adj_close_after_1[date(2024, 1, 5)] == pytest.approx(51_000)
    assert adj_close_after_1[date(2024, 1, 8)] == pytest.approx(52_000)

    # 추가 4회 반복 (총 5회) — idempotent 검증
    for _ in range(4):
        rerun_result = job.run()
        assert rerun_result.success is True

    # 5회 후 adj_close가 1회 후와 완전히 동일한지 (누적 적용 X)
    fresh = session_factory()
    try:
        rows_after_5 = repositories.get_price_range(
            fresh, SYMBOL, date(2024, 1, 2), date(2024, 1, 8)
        )
    finally:
        fresh.close()
    for r in rows_after_5:
        # 14.5 / 13.7 핵심: 동일 입력 동일 출력
        assert r.adj_close == pytest.approx(adj_close_after_1[r.date]), (
            f"date={r.date} 5회 후 adj_close가 1회 후와 다름 — 누적 적용 발생 (14.5 위반)"
        )
        # 13.7: close (원 가격)는 절대 변하지 않음
    fresh = session_factory()
    try:
        for r in repositories.get_price_range(
            fresh, SYMBOL, date(2024, 1, 2), date(2024, 1, 8)
        ):
            seed = next(s for s in rows_seed if s["date"] == r.date)
            assert r.close == seed["close"], (
                f"date={r.date} close 변경됨 — 13.7 close 보존 위반"
            )
    finally:
        fresh.close()


# ---------------------------------------------------------------------------
# 시나리오 4: UniverseSnapshotJob → universe_history → 재현 (config_hash 기반)
# ---------------------------------------------------------------------------


def test_universe_snapshot_persists_and_reproduces_via_config_hash(
    session_factory, db_session
):
    """028 UniverseSnapshotJob → 027 universe_history 영속화 → 동일 config 재실행 시 동일 row.

    검증:
        - 13.13 / 14.10 (생존편향 — 폐지 종목도 그 시점에 살아있었으면 보존)
        - 13.12 (결정론 — symbols_json은 symbol ASC, config_hash 안정)
        - 027 UniqueConstraint(as_of_date, market, selection_method, config_hash) 동작

    시나리오:
        1. 종목 4개 시드 (3개 활성 + 1개는 2024-02-01 폐지 예정)
        2. as_of_date=2024-01-02 시점에 universe 선정 (4개 모두 활성) → 잡 실행
        3. config_hash가 안정 해시인지 확인 + symbols_json이 symbol ASC인지
        4. 동일 config로 잡 재실행 → upsert (UniqueConstraint 충돌 없이 갱신)
        5. 재현: 같은 config_hash로 universe_history 조회 시 동일 symbols_json 반환
    """
    AS_OF = date(2024, 1, 2)
    # 4개 종목 시드 — 1개는 2024-02-01 폐지 예정 (시점=AS_OF에는 살아있음)
    for code in ["000001", "000002", "000003"]:
        repositories.upsert_symbol(
            db_session,
            {
                "symbol": code, "name": f"종목{code}",
                "market": "KOSPI", "listing_date": date(2020, 1, 1),
            },
        )
    # 13.13 생존편향: 폐지 예정 종목도 AS_OF 시점에는 universe에 포함되어야 함
    repositories.upsert_symbol(
        db_session,
        {
            "symbol": "000099", "name": "폐지예정종목",
            "market": "KOSPI", "listing_date": date(2020, 1, 1),
            "delisting_date": date(2024, 2, 1),  # AS_OF(2024-01-02)보다 미래
        },
    )
    db_session.commit()

    selector_config = {
        "market": "KOSPI",
        "selection_method": SELECTION_METHOD_ALL,
    }
    job = UniverseSnapshotJob(
        config=UniverseSnapshotConfig(
            as_of_date=AS_OF,
            selector_config=selector_config,
        ),
        session_factory=session_factory,
    )

    # 1회차 실행
    result1 = job.run()
    assert result1.success is True
    stats1 = dict(result1.stats)
    # 13.13: 폐지 예정 종목 (000099)도 포함되어야 함 (AS_OF에 살아있음)
    assert stats1["symbols_selected"] == 4

    # 영속화 검증
    fresh = session_factory()
    try:
        snaps = fresh.query(UniverseHistory).all()
        assert len(snaps) == 1
        snap = snaps[0]
        # 13.12: symbols_json은 symbol ASC
        assert snap.symbols_json == ["000001", "000002", "000003", "000099"]
        # 027: config_hash가 안정 해시
        assert snap.config_hash is not None
        assert snap.config_hash == compute_config_hash(selector_config)
    finally:
        fresh.close()

    # 2회차 실행 (같은 config) — UniqueConstraint 갱신 (행 수 1 유지)
    result2 = job.run()
    assert result2.success is True

    fresh = session_factory()
    try:
        snaps = fresh.query(UniverseHistory).all()
        assert len(snaps) == 1, "동일 config_hash 재실행 시 새 row 생성 금지 (upsert)"
        # 재현 검증: universe_history.symbols_json이 동일 종목 리스트
        snap = snaps[0]
        assert snap.symbols_json == ["000001", "000002", "000003", "000099"]
        # 13.12 결정론: 두 번 호출 시 동일 config_hash
        assert snap.config_hash == compute_config_hash(selector_config)
    finally:
        fresh.close()

    # config가 다르면 (selection_method 변경) 별도 row 생성
    selector_config_diff = {
        "market": "KOSPI",
        "selection_method": SELECTION_METHOD_ALL,
        "exclude_etf": True,  # 추가 키
    }
    job_diff = UniverseSnapshotJob(
        config=UniverseSnapshotConfig(
            as_of_date=AS_OF,
            selector_config=selector_config_diff,
        ),
        session_factory=session_factory,
    )
    job_diff.run()

    fresh = session_factory()
    try:
        snaps = fresh.query(UniverseHistory).order_by(UniverseHistory.id).all()
        # 027 UniqueConstraint: config_hash가 다르면 별도 row
        assert len(snaps) == 2
        assert snaps[0].config_hash != snaps[1].config_hash
    finally:
        fresh.close()


# ---------------------------------------------------------------------------
# 시나리오 5: MissingDataCheckJob — trading_calendar에 거래일이지만 daily_prices 결손
# ---------------------------------------------------------------------------


def test_missing_data_check_detects_gaps_without_filling(
    session_factory, db_session
):
    """028 MissingDataCheckJob — trading_calendar 거래일 vs daily_prices 결손 감지.

    14.10 핵심 정합: "forward-fill 금지" — 본 잡은 결손을 감지만 하며
    DailyPrice를 자동 생성하지 않는다.

    시나리오:
        1. 종목 1개 시드
        2. 거래일 5일 시드 (2024-01-02 ~ 2024-01-08, 주말 제외)
        3. daily_prices 3건 시드 (01-03, 01-08 결손)
        4. MissingDataCheckJob 실행 → 결손 2건 감지 (last_alert.entries)
        5. **DB 변경 0건** — 잡 실행 후에도 daily_prices는 여전히 3건
    """
    SYMBOL = "005930"

    # 종목 시드
    repositories.upsert_symbol(
        db_session,
        {
            "symbol": SYMBOL, "name": "삼성전자",
            "market": "KOSPI", "listing_date": date(2020, 1, 1),
        },
    )

    # 거래일 5일 시드
    trading_dates = [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
    ]
    for d in trading_dates:
        repositories.upsert_trading_day(
            db_session, date=d, market="KOSPI", is_trading_day=True
        )

    # daily_prices는 3건만 시드 (01-03 결손, 01-08 결손)
    present_dates = [date(2024, 1, 2), date(2024, 1, 4), date(2024, 1, 5)]
    rows_present = [
        {
            "symbol": SYMBOL, "date": d,
            "open": 70_000, "high": 70_500, "low": 69_500, "close": 70_000,
            "volume": 1_000_000,
            "adj_open": 70_000, "adj_high": 70_500, "adj_low": 69_500, "adj_close": 70_000,
            "adj_volume": 1_000_000,
        }
        for d in present_dates
    ]
    repositories.bulk_upsert_daily_prices(db_session, rows_present)
    db_session.commit()

    # 결손 검사 잡 실행
    job = MissingDataCheckJob(
        config=MissingDataCheckConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 8),
            market="KOSPI",
            symbols=(SYMBOL,),
        ),
        session_factory=session_factory,
    )

    # 잡 실행 전 DailyPrice 카운트
    fresh = session_factory()
    try:
        before_count = fresh.query(DailyPrice).count()
    finally:
        fresh.close()
    assert before_count == 3

    result = job.run()

    assert result.success is True
    stats = dict(result.stats)
    assert stats["trading_days"] == 5
    assert stats["symbols_checked"] == 1
    # 14.13: 결손 2건 감지 (01-03, 01-08)
    assert stats["missing_count"] == 2
    assert stats["missing_symbols"] == 1
    # warnings에 결손 카운트 누적
    assert any("결손 감지" in w for w in result.warnings)

    # MissingDataAlert 상세 검증 (결정론: symbol ASC, date ASC)
    alert = job.last_alert
    assert alert.missing_count == 2
    assert alert.entries == (
        # symbol ASC, date ASC 정렬 — 단일 종목이므로 date ASC
        # MissingDataEntry equality는 frozen dataclass라 모든 필드 일치
        type(alert.entries[0])(symbol=SYMBOL, date=date(2024, 1, 3), market="KOSPI"),
        type(alert.entries[0])(symbol=SYMBOL, date=date(2024, 1, 8), market="KOSPI"),
    )

    # 14.10 핵심 검증: 잡 실행 후에도 DailyPrice 카운트 변동 없음 (forward-fill 금지)
    fresh = session_factory()
    try:
        after_count = fresh.query(DailyPrice).count()
    finally:
        fresh.close()
    assert after_count == before_count, (
        f"MissingDataCheckJob이 결손을 자동으로 채웠음 (14.10 forward-fill 금지 위반): "
        f"before={before_count} after={after_count}"
    )
