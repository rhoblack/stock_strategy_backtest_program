"""Phase 10 e2e 통합 시나리오 — BacktestEngine 다종목 + priority + 한도 + event_log.

Phase 10 step 020/021/022/023이 도입한 4개 핵심 영역의 cross-component
contract를 보호한다. 각 step의 단위 테스트는 자체 영역만 검증하므로,
본 통합 테스트는 4개 영역이 동일 BacktestEngine 인스턴스 안에서 협업할 때
**결정론 + look-ahead 차단 + 정확성 정책 13.x 준수**를 e2e로 회귀 보호한다.

검증 매핑 (정확성 정책 13.x):
    - 13.4.3 (상한가 매수 차단)              → 시나리오 3
    - 13.4.4 (거래량 0 / 거래정지 event_log) → 시나리오 1·2 (간접 — 5종목 fixture는
                                              거래정지 row 없음)
    - 13.4.5 (상장폐지 강제 매도)            → 시나리오 2
    - 13.8   (priority + 한도 흐름)          → 시나리오 1
    - 13.12  (결정론 — dict 순회 금지)        → 시나리오 1·4
    - 13.12.2 (random_seed 정책)             → priority 단위 테스트가 별도 검증
    - 13.13  (생존편향 — 폐지 종목 청산 보존) → 시나리오 2 (universe와 분리된 강제 매도 흐름)
    - 13.15  (look-ahead — 미래 데이터 차단)  → 시나리오 4 (Phase 9 + Phase 10 통합)
    - 04.6/§11 (일별 루프 + priority + 한도) → 시나리오 1·4
    - CLAUDE.md #8 (결정론)                   → 시나리오 1·2·3·4

본 모듈은 의도적으로 단일 종목 골든 fixture에는 없는 다종목/한도/상한가/폐지
시나리오만을 다룬다 — 단일 종목 경로는 Phase 1 골든이 frozen 9지표로 보호.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

# 5개 기본 조건 자동 등록 (price_vs_ma 등)
import app.strategy  # noqa: F401
from app.backtest.config import BacktestConfig
from app.backtest.engine import (
    EVENT_REASON_FORCE_SELL_DELISTED,
    EVENT_REASON_LIMIT_UP_BUY,
    EVENT_REASON_MAX_POSITIONS,
    EVENT_TYPE_FORCE_SELL,
    EVENT_TYPE_SKIP,
    BacktestEngine,
)
from app.backtest.execution import ExecutionModel
from app.db.session import (
    create_db_engine,
    drop_db,
    init_db,
    make_session_factory,
)
from app.market_data.local_csv import LocalCsvProvider
from app.market_data.price_loader import PriceLoader
from app.market_data.universe import (
    SELECTION_METHOD_ALL,
    UniverseSelector,
)
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

# Phase 9에서 만들어 둔 universe_test fixture 그대로 재사용 (Phase 9 e2e와 동일).
FIXTURE_ROOT = (
    Path(__file__).parent.parent
    / "market_data"
    / "fixtures"
    / "csv"
    / "universe_test"
)


SYMBOL_A = "000001"
SYMBOL_B = "000002"
SYMBOL_C = "000003"
SYMBOL_D = "000004"


# ---------------------------------------------------------------------------
# 헬퍼 (단위 테스트와 동일한 시그니처)
# ---------------------------------------------------------------------------


def _make_df(
    dates: list[date],
    closes: list[float],
    *,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
    is_limit_up: list[bool] | None = None,
) -> pd.DataFrame:
    """단위 테스트 헬퍼와 동일한 DataFrame 빌더."""
    n = len(dates)
    if opens is None:
        opens = closes
    if highs is None:
        highs = [max(o, c) for o, c in zip(opens, closes, strict=True)]
    if lows is None:
        lows = [min(o, c) for o, c in zip(opens, closes, strict=True)]
    if volumes is None:
        volumes = [10_000.0] * n

    data = {
        "date": dates,
        "adj_open": opens,
        "adj_high": highs,
        "adj_low": lows,
        "adj_close": closes,
        "adj_volume": volumes,
    }
    if is_limit_up is not None:
        data["is_limit_up"] = is_limit_up

    df = pd.DataFrame(data)
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    return df


def _trivial_entry_strategy() -> dict:
    """가격 > MA(2) entry — 단순 시계열 신호 (단위 테스트와 동일)."""
    return {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        }
    }


def _make_engine(
    *,
    initial_cash: float = 5_000_000,
    position_size: float = 500_000,
    priority_method: str = "none",
    random_seed: int | None = None,
    max_positions: int | None = None,
    max_daily_entries: int | None = None,
    daily_buy_budget: float | None = None,
    allow_buy_limit_up: bool = False,
) -> BacktestEngine:
    portfolio = Portfolio(initial_cash=initial_cash)
    execution_model = ExecutionModel(
        fee_rate=0.0,
        tax_rate=0.0,
        slippage=0.0,
        tick_rounding="nearest",
    )
    config = BacktestConfig(
        symbol=SYMBOL_A,
        start_date=date(2024, 1, 1),
        end_date=date(2030, 12, 31),
        position_size_amount=position_size,
        initial_cash=initial_cash,
        priority_method=priority_method,
        random_seed=random_seed,
        max_positions=max_positions,
        max_daily_entries=max_daily_entries,
        daily_buy_budget=daily_buy_budget,
        allow_buy_limit_up=allow_buy_limit_up,
    )
    return BacktestEngine(
        StrategyEngine(_trivial_entry_strategy()),
        portfolio,
        execution_model,
        config,
    )


# ---------------------------------------------------------------------------
# 시나리오 1: 다종목 priority(trading_value_desc) + max_positions e2e
# ---------------------------------------------------------------------------


def test_multi_symbol_priority_then_max_positions_orders_and_caps():
    """3종목 동시 entry → trading_value_desc로 정렬 → max_positions=2 cap.

    검증 (정확성 정책 13.8 + CLAUDE.md #8):
        1. 3종목 모두 같은 today에 final_entry_signal=True가 되도록 시계열 구성
        2. priority_method="trading_value_desc": close × volume 내림차순 +
           symbol ASC tie-breaker
        3. max_positions=2: priority 1·2위만 매수, 3위는 skip + event_log
           (skip_max_positions)
        4. 매수된 종목의 trade_executions는 priority 순서를 그대로 따름
        5. event_log에 max_positions skip 사유가 정확히 1건 기록 (3 - 2 = 1)

    이 시나리오는 020(다종목) + 021(priority) + 022(max_positions) + 023
    (event_log) 4개 step의 cross-component contract를 한 번에 검증한다.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    # 3종목 모두 같은 신호 — close가 단조증가 → MA(2) 대비 > 조건 동일 시점에 충족.
    # priority 결정: A=close*volume=130_000, B=260_000, C=390_000 (last row)
    #   → priority 순서: C → B → A (trading_value_desc).
    df_a = _make_df(dates, closes=[100, 100, 110, 120, 130], volumes=[1_000.0] * 5)
    df_b = _make_df(dates, closes=[200, 200, 210, 220, 230], volumes=[1_000.0] * 5)
    df_c = _make_df(dates, closes=[300, 300, 310, 320, 330], volumes=[1_000.0] * 5)
    prices = {SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c}

    # initial_cash=2_000_000 + position_size=500_000 → 4종목 매수 가능.
    # max_positions=2로 명시 cap → 우선 2개만 매수.
    engine = _make_engine(
        initial_cash=2_000_000,
        position_size=500_000,
        priority_method="trading_value_desc",
        max_positions=2,
    )
    result = engine.run(prices)

    # 매수된 종목들 (entry execution_type)
    buys = [
        ex for ex in result.trade_executions if ex["execution_type"] == "BUY"
    ]
    bought_symbols_in_order = [ex["symbol"] for ex in buys]

    # 정확히 2종목만 매수 (max_positions=2)
    assert len(buys) == 2, (
        f"max_positions=2인데 매수가 {len(buys)}건 발생: {bought_symbols_in_order}"
    )
    # priority 순서: trading_value_desc → C(330*1000) > B > A
    # 첫 entry 후 holding_count=1, 두 번째도 같은 today에 들어가야 정렬 검증 가능.
    # 같은 today에 발생한 entry signal_date 기준 우선순위 확인.
    first_signal = buys[0]["signal_date"]
    same_day_buys = [ex for ex in buys if ex["signal_date"] == first_signal]
    assert len(same_day_buys) >= 2, (
        "priority 정렬 검증 위해 같은 today에 ≥2건 매수 필요 — "
        f"실제: {[(ex['symbol'], ex['signal_date']) for ex in buys]}"
    )
    # 같은 today 내에서 priority가 적용되었는지 (C가 B보다 먼저)
    same_day_symbols = [ex["symbol"] for ex in same_day_buys]
    assert same_day_symbols.index(SYMBOL_C) < same_day_symbols.index(SYMBOL_B), (
        f"trading_value_desc 정렬 위반: {same_day_symbols}"
    )

    # max_positions로 잘려나간 후보(A) skip event_log 1건 (같은 today)
    max_pos_skips = [
        e
        for e in result.event_log
        if e["reason"] == EVENT_REASON_MAX_POSITIONS and e["date"] == first_signal
    ]
    assert len(max_pos_skips) == 1, (
        f"max_positions skip event 정확히 1건 기대, 실제 {len(max_pos_skips)}건: "
        f"{max_pos_skips}"
    )
    assert max_pos_skips[0]["symbol"] == SYMBOL_A
    assert max_pos_skips[0]["event_type"] == EVENT_TYPE_SKIP
    # detail에 한도 컨텍스트가 있는지 (결정론적 사유 추적)
    assert "max_positions" in max_pos_skips[0]["detail"]
    assert max_pos_skips[0]["detail"]["max_positions"] == 2


# ---------------------------------------------------------------------------
# 시나리오 2: 상장폐지 강제 매도 — universe_resolver와 무관한 보유 청산
# ---------------------------------------------------------------------------


def test_delisted_symbol_force_sold_at_today_close_independent_of_universe():
    """today=폐지일에 보유 중인 종목은 universe_resolver 결과와 무관하게 강제 매도.

    검증 (정확성 정책 13.4.5 + 13.13):
        1. SYMBOL_A를 미리 매수해 보유 상태로 만든다 (entry signal 충족 시점)
        2. 다음 거래일(폐지일)에 universe_resolver는 SYMBOL_A를 제외 (생존편향
           완화 + 13.13)
        3. 그러나 _force_sell_delisted_today가 보유 평가 *이전*에 호출되어
           당일 adj_close로 강제 청산
        4. event_log에 force_sell_delisted 1건 기록
        5. trade_executions에 폐지일 매도 + reason=force_sell_delisted

    이 시나리오는 step 023의 핵심 정합 결정 (delisting_dates는 universe_resolver
    와 분리되어 있으며 보유 청산만 담당)을 e2e로 보호한다.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    # MA(2) entry: 12일에 close=110 > MA(2)=105 → 12일 신호 → 15일 매수.
    # 16일을 폐지일로 (보유 상태에서 강제 청산되도록).
    df_a = _make_df(dates, closes=[100, 100, 110, 110, 110, 110])
    prices = {SYMBOL_A: df_a}

    # universe_resolver: 폐지일(16)부터 SYMBOL_A를 universe에서 제외.
    # 13.13 — 보유 청산은 universe와 무관해야 한다.
    delisting_date = date(2024, 1, 16)

    def universe_resolver(today: date) -> list[str]:
        if today >= delisting_date:
            return []
        return [SYMBOL_A]

    engine = _make_engine(initial_cash=2_000_000, position_size=500_000)
    result = engine.run(
        prices,
        universe_resolver=universe_resolver,
        delisting_dates={SYMBOL_A: delisting_date},
    )

    # event_log에 force_sell_delisted 정확히 1건 (폐지일에)
    force_sell_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_FORCE_SELL_DELISTED
    ]
    assert len(force_sell_events) == 1, (
        f"force_sell_delisted 정확히 1건 기대, 실제 {len(force_sell_events)}건: "
        f"{force_sell_events}"
    )
    event = force_sell_events[0]
    assert event["symbol"] == SYMBOL_A
    assert event["event_type"] == EVENT_TYPE_FORCE_SELL
    assert event["date"] == delisting_date
    # 청산가가 당일 adj_close (= 110)인지 — 13.4.5의 "정리매매 마지막 종가" 정합
    assert event["detail"]["exit_price"] == 110.0

    # 매수 1건 + 폐지일 매도 1건이 trade_executions에 모두 있어야 함
    sells = [ex for ex in result.trade_executions if ex["execution_type"] == "SELL"]
    assert len(sells) == 1
    delisted_sell = sells[0]
    assert delisted_sell["symbol"] == SYMBOL_A
    assert delisted_sell["reason"] == EVENT_REASON_FORCE_SELL_DELISTED
    # 강제 매도는 today 즉시 체결 → execution_date = signal_date = 폐지일
    assert delisted_sell["date"] == delisting_date

    # 종료 시점 보유 0 (폐지일에 모두 청산됨)
    assert engine.portfolio.positions_count() == 0


# ---------------------------------------------------------------------------
# 시나리오 3: 상한가 매수 차단 + BacktestResult.event_log 영속화 인터페이스
# ---------------------------------------------------------------------------


def test_limit_up_blocks_buy_and_event_log_exposed_via_result():
    """신호일이 상한가면 매수 차단 + BacktestResult.event_log에 노출.

    검증 (정확성 정책 13.4.3):
        1. SYMBOL_A의 신호일에 is_limit_up=True 컬럼 명시 (PriceLoader-friendly)
        2. default allow_buy_limit_up=False → 매수 차단
        3. event_log에 skip_limit_up_buy 1건 기록
        4. BacktestResult.event_log가 BacktestEngine.event_log 사본 (영속화 인터페이스)
        5. trade_executions에 매수 0건 (차단됐으므로)

    이 시나리오는 023의 BacktestResult.event_log 인터페이스가 service/DB 영속화
    레이어가 후속 step에서 매핑할 수 있는 형태로 노출되는지 보장한다.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # 11일에 신호 충족 (close 단조증가) → 12일이 신호일. 12일을 상한가로.
    df_a = _make_df(
        dates,
        closes=[100, 100, 110, 110],
        is_limit_up=[False, False, True, False],
    )

    engine = _make_engine(initial_cash=2_000_000, position_size=500_000)
    result = engine.run({SYMBOL_A: df_a})

    # event_log: skip_limit_up_buy 정확히 1건
    limit_up_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_LIMIT_UP_BUY
    ]
    assert len(limit_up_events) == 1, (
        f"skip_limit_up_buy 정확히 1건 기대, 실제 {len(limit_up_events)}건: "
        f"{limit_up_events}"
    )
    assert limit_up_events[0]["symbol"] == SYMBOL_A
    assert limit_up_events[0]["event_type"] == EVENT_TYPE_SKIP

    # 매수 0건 (차단됨)
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buys) == 0, f"상한가 매수 차단 실패 — buys: {buys}"

    # BacktestResult.event_log가 BacktestEngine.event_log 사본인지
    assert result.event_log == engine.event_log
    assert result.event_log is not engine.event_log  # list 사본 (mutation 차단)


# ---------------------------------------------------------------------------
# 시나리오 4: Phase 9 (UniverseSelector + PriceLoader) + Phase 10 (BacktestEngine)
# ---------------------------------------------------------------------------


@pytest.fixture
def loaded_session():
    """in-memory DB + universe_test fixture 적재 (Phase 9 e2e와 동일 fixture 재사용)."""
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    SessionLocal = make_session_factory(engine)
    session = SessionLocal()
    try:
        LocalCsvProvider(root=FIXTURE_ROOT).ingest_into(session)
        session.commit()
        yield session
    finally:
        session.close()
        drop_db(engine)
        engine.dispose()


def test_universe_priceloader_then_multi_symbol_engine_roundtrip(loaded_session):
    """Phase 9 (UniverseSelector + PriceLoader) → Phase 10 BacktestEngine 다종목 e2e.

    Phase 9 e2e가 검증한 (UniverseSelector → PriceLoader → BacktestEngine 단일
    종목) 라운드트립을 Phase 10 다종목으로 확장 — 016~023 4단계 컴포넌트가
    동일 BacktestEngine 인스턴스에서 협업할 때 결정론과 컬럼 명세가 모두 통과.

    검증 (정확성 정책 13.7 + 13.13 + 13.15 + CLAUDE.md #8):
        1. UniverseSelector.select가 default exclude로 5개 일반 종목 반환 (KOSPI)
        2. 각 선정 종목을 PriceLoader.load로 로드 → BacktestEngine 입력
           명세 (PRICE_LOADER_COLUMNS) 충족
        3. BacktestEngine.run(prices_dict, universe_resolver) 다종목 입력
        4. 결정론: 동일 입력 3회 반복 → final_equity / 매수 종목 순서 동일
        5. event_log는 빈 list 또는 해석 가능 (fixture에 거래정지/상한가 없음)
        6. Phase 9 정합 (PriceLoader가 채운 next_*) + Phase 10 정합 (다종목 입력)
           모두 통과
    """
    selector = UniverseSelector(loaded_session)
    loader = PriceLoader(loaded_session)

    universe = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
        },
        as_of_date=date(2024, 1, 8),
    )
    selected_symbols = sorted(s.symbol for s in universe)
    # Phase 9 e2e가 검증한 default exclude 결과 — 5개 일반 KOSPI 종목.
    assert selected_symbols == ["000001", "000002", "000003", "000004", "000005"]

    # 각 종목에 대해 PriceLoader.load → 다종목 dict 구성.
    prices: dict[str, pd.DataFrame] = {}
    for symbol in selected_symbols:
        df = loader.load(
            symbol=symbol,
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 8),
        )
        # PriceLoader가 채운 컬럼이 BacktestEngine이 기대하는 명세 — 015 정합
        # + Phase 10 다종목 호환의 핵심.
        for required_col in (
            "date",
            "adj_open",
            "adj_high",
            "adj_low",
            "adj_close",
            "adj_volume",
            "next_open",
            "next_volume",
        ):
            assert required_col in df.columns, (
                f"PriceLoader가 BacktestEngine 필수 컬럼 누락: {required_col} "
                f"(symbol={symbol})"
            )
        prices[symbol] = df

    # 결정론 검증 — 동일 입력 3회 반복 (rng 미사용 method라도 dict 순회 의존이
    # 있으면 깨질 수 있음).
    final_equities: list[float] = []
    bought_orders: list[tuple[str, ...]] = []
    for _ in range(3):
        engine = _make_engine(
            initial_cash=2_000_000,
            position_size=500_000,
            priority_method="trading_value_desc",
            max_positions=2,
        )
        # universe_resolver: PriceLoader가 가진 종목만 (Phase 9 → Phase 10 contract)
        result = engine.run(
            prices,
            universe_resolver=lambda today: selected_symbols,
        )
        final_equities.append(result.final_equity)
        buys = [
            ex["symbol"]
            for ex in result.trade_executions
            if ex["execution_type"] == "BUY"
        ]
        bought_orders.append(tuple(buys))

    assert len(set(final_equities)) == 1, (
        f"결정론 깨짐 — final_equity 3회 반복: {final_equities}"
    )
    assert len(set(bought_orders)) == 1, (
        f"결정론 깨짐 — 매수 종목 순서 3회 반복: {bought_orders}"
    )

    # max_positions=2 → 최대 2개 종목 보유. fixture 5종목 모두에 entry signal이
    # 발생하지 않더라도 매수가 발생한 경우 수가 max_positions 이하여야 함.
    final_buy_count = len(bought_orders[0])
    held_at_end = engine.portfolio.positions_count()
    assert held_at_end <= 2, (
        f"max_positions=2 위반 — 종료 시 보유 {held_at_end}종목"
    )
    # universe_test fixture는 거래정지/상한가/폐지가 보유 평가일에 도달하는
    # 시나리오가 없으므로 event_log는 매수 후보 한도 skip만 가능.
    # (있어도 모두 알려진 사유 코드인지만 화이트리스트로 검증.)
    known_reasons = {
        "skip_no_volume",
        "skip_limit_up_buy",
        "skip_limit_down_sell",
        "skip_max_positions",
        "skip_max_daily_entries",
        "skip_daily_buy_budget",
        "skip_max_gap",
        "force_sell_delisted",
    }
    for event in result.event_log:
        assert event["reason"] in known_reasons, (
            f"알 수 없는 event reason: {event['reason']}"
        )

    # 정상 매수가 발생한 경우 priority 순서가 trading_value_desc + symbol ASC를 따름
    # (이미 결정론으로 동일 순서가 3회 반복되었음 — 그 순서가 priority 정책 정합인지
    # 추가 검증)
    if final_buy_count > 0:
        # fixture의 close * volume:
        #   000001: 10400 * 1.4M = 14,560,000,000
        #   000002: 20400 * 0.58M = 11,832,000,000
        #   000003: 30400 * 0.34M = 10,336,000,000
        #   000004: 40400 * 0.24M = 9,696,000,000
        #   000005: 50400 * 0.14M = 7,056,000,000
        # priority trading_value_desc → 000001 > 000002 > ... → 매수 순서도 동일.
        # 첫 매수가 항상 000001(가장 높은 trading_value)이어야 함.
        assert bought_orders[0][0] == "000001", (
            f"trading_value_desc 1순위 위반 — 첫 매수: {bought_orders[0]}"
        )
