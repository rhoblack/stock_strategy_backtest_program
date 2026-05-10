"""Phase 9 e2e 통합 시나리오 — UniverseSelector + PriceLoader + BacktestEngine.

본 테스트는 step 015~019에서 도입된 4개 컴포넌트 (LocalCsvProvider /
repositories / UniverseSelector / PriceLoader)가 동일한 SQLAlchemy Session을
공유하면서 BacktestEngine이 기대하는 입력까지 한 번에 연결되는지 확인한다.
step 단위 단위 테스트는 각 컴포넌트 내부만 검증하므로, 컴포넌트 간 contract
회귀를 별도로 보호한다.

검증 매핑:
    - 06번 §8 (UniverseSelector 공통 필터) → 폐지/미래 상장 종목 제외
    - 13번 §7 (수정주가) — PriceLoader가 close + adj_close 모두 노출
    - 13번 §13.13 (생존편향) — delisting 종목이 폐지 후 universe에서 제외
    - 13번 §13.15 (look-ahead) — UniverseSelector + PriceLoader는 미래 데이터 미사용
    - 015 (signal_date vs execution_date 분리) — PriceLoader DataFrame이
      BacktestEngine.run을 끝까지 통과
    - CLAUDE.md #8 (결정론) — symbol ASC tie-breaker 일관성

외부 fetch: 0건. fixture는 backend/tests/market_data/fixtures/csv/universe_test/.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.db.session import (
    create_db_engine,
    drop_db,
    init_db,
    make_session_factory,
)
from app.market_data.local_csv import LocalCsvProvider
from app.market_data.price_loader import (
    PRICE_LOADER_COLUMNS,
    PriceLoader,
)
from app.market_data.universe import (
    SELECTION_METHOD_ALL,
    UniverseSelector,
)

FIXTURE_ROOT = (
    Path(__file__).parent.parent
    / "market_data"
    / "fixtures"
    / "csv"
    / "universe_test"
)
AS_OF_DATE = date(2024, 1, 8)
LOAD_START = date(2024, 1, 2)
LOAD_END = date(2024, 1, 8)

# universe_test fixture 메타 — 기대 결과와의 정합성을 명시 (회귀 발생 시 추적성).
EXPECTED_KOSPI_ALL_DEFAULT = ["000001", "000002", "000003", "000004", "000005"]
EXPECTED_DELISTED_BEFORE_AS_OF = "000020"  # delisting_date=2024-01-04
EXPECTED_FUTURE_LISTED = "000030"  # listing_date=2024-01-09


@pytest.fixture
def loaded_session():
    """in-memory DB + universe_test fixture 적재된 세션."""
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


# ---------------------------------------------------------------------------
# 시나리오 1: UniverseSelector → PriceLoader 라운드트립
# ---------------------------------------------------------------------------


def test_universe_priceloader_roundtrip_yields_engine_compatible_dataframes(
    loaded_session,
):
    """선정된 universe의 모든 종목을 PriceLoader로 로드 → 컬럼 명세 일치.

    검증:
        1. UniverseSelector.select가 default exclude로 5개 일반 종목만 반환
           (폐지 / 미래 상장 / ETF / 우선주 등 제외 — 13.13 / 06.8)
        2. 각 선정 종목에 대해 PriceLoader.load가 BacktestEngine 호환 컬럼 명세
           (PRICE_LOADER_COLUMNS) 그대로 반환 — 015 정합
        3. close + adj_close 모두 NOT NULL — 13.7 수정주가 정책
    """
    selector = UniverseSelector(loaded_session)
    loader = PriceLoader(loaded_session)

    universe = selector.select(
        config={
            "market": "KOSPI",
            "selection_method": SELECTION_METHOD_ALL,
        },
        as_of_date=AS_OF_DATE,
    )

    codes = [s.symbol for s in universe]
    assert codes == EXPECTED_KOSPI_ALL_DEFAULT, (
        "06.8 default exclude + 13.13 동적 listing/delisting 필터 회귀: "
        f"{codes}"
    )

    # 각 선정 종목을 PriceLoader로 로드 — 컬럼 명세 일치
    for symbol_obj in universe:
        df = loader.load(symbol_obj.symbol, LOAD_START, LOAD_END)
        # 14.10 결손 정책: forward-fill 금지 → DB row 그대로
        assert len(df) >= 1, f"{symbol_obj.symbol} fixture에 가격 row 없음"
        # 015 정합: BacktestEngine이 보는 컬럼 명세 정확히 일치
        assert list(df.columns) == list(PRICE_LOADER_COLUMNS), (
            f"{symbol_obj.symbol} PriceLoader 컬럼 명세 불일치 — 015 회귀 가능"
        )
        # 13.7: close + adj_close 모두 NOT NULL
        assert df["close"].notna().all(), f"{symbol_obj.symbol} close NaN 발견"
        assert df["adj_close"].notna().all(), (
            f"{symbol_obj.symbol} adj_close NaN — 13.7 수정주가 정책 위반"
        )


# ---------------------------------------------------------------------------
# 시나리오 2: 13.13 생존편향 — 폐지 종목은 universe에서 제외되지만 가격은 보존
# ---------------------------------------------------------------------------


def test_delisted_symbol_excluded_from_universe_but_prices_remain(loaded_session):
    """폐지 종목은 폐지일 이후 universe에서 제외되지만 가격 row는 보존.

    14번 §10 생존편향 보존 정책:
        - delisting된 종목의 daily_prices는 그대로 보존되어야 함
        - 단, UniverseSelector는 as_of_date >= delisting_date인 종목을 제외
    """
    selector = UniverseSelector(loaded_session)
    loader = PriceLoader(loaded_session)

    # AS_OF_DATE = 2024-01-08, 폐지 종목 000020의 delisting_date = 2024-01-04
    universe = selector.select(
        config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in universe]
    assert EXPECTED_DELISTED_BEFORE_AS_OF not in codes, (
        "13.13 생존편향: 폐지 종목이 폐지 후 universe에 남아있음"
    )

    # 그러나 가격 row는 보존되어 있어야 함 (14.10)
    df = loader.load(EXPECTED_DELISTED_BEFORE_AS_OF, LOAD_START, LOAD_END)
    assert len(df) >= 1, (
        "14.10 생존편향 보존 정책 위반: 폐지 종목의 가격 row까지 사라짐. "
        "과거 백테스트에서 해당 종목의 거래는 폐지일 전까지는 정상 평가되어야 함"
    )


# ---------------------------------------------------------------------------
# 시나리오 3: 13.15 look-ahead — 미래 상장 종목은 어떤 시점에서도 미래 데이터 미사용
# ---------------------------------------------------------------------------


def test_future_listed_symbol_excluded_when_as_of_before_listing(loaded_session):
    """as_of_date < listing_date인 종목은 universe에서 제외 (13.15 look-ahead).

    fixture: 000030의 listing_date = 2024-01-09 → AS_OF_DATE = 2024-01-08
    시점에는 universe에 포함되어선 안 됨.
    """
    selector = UniverseSelector(loaded_session)

    universe = selector.select(
        config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
        as_of_date=AS_OF_DATE,
    )
    codes = [s.symbol for s in universe]
    assert EXPECTED_FUTURE_LISTED not in codes, (
        "13.15 look-ahead 차단 위반: 미래 상장 종목이 상장 전 universe에 포함됨"
    )


# ---------------------------------------------------------------------------
# 시나리오 4: 결정론 — UniverseSelector는 항상 symbol ASC, 5회 반복 동일
# ---------------------------------------------------------------------------


def test_universe_priceloader_pipeline_is_deterministic(loaded_session):
    """동일 입력 → UniverseSelector + PriceLoader 결과가 5회 반복 동일.

    CLAUDE.md #8 / 13.12 결정론 정책. universe_test fixture가 단순하므로
    set/dict 순서 의존성이 있다면 즉시 발견 가능.
    """
    selector = UniverseSelector(loaded_session)
    loader = PriceLoader(loaded_session)

    runs: list[tuple[list[str], list[int]]] = []
    for _ in range(5):
        universe = selector.select(
            config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
            as_of_date=AS_OF_DATE,
        )
        codes = [s.symbol for s in universe]
        # 각 종목의 row count도 함께 비교 (PriceLoader 결정론)
        row_counts = [
            len(loader.load(s.symbol, LOAD_START, LOAD_END)) for s in universe
        ]
        runs.append((codes, row_counts))

    first = runs[0]
    for i, run in enumerate(runs[1:], start=2):
        assert run == first, (
            f"결정론 위반: run #1과 run #{i}이 다름.\n"
            f"  #1: {first}\n"
            f"  #{i}: {run}"
        )


# ---------------------------------------------------------------------------
# 시나리오 5: BacktestEngine 호환 — 선정된 종목 1개를 엔진에 그대로 투입
# ---------------------------------------------------------------------------


def test_universe_selected_symbol_runs_through_backtest_engine(loaded_session):
    """UniverseSelector → PriceLoader → BacktestEngine.run 끝까지 통과.

    015 정합 회귀: PriceLoader가 만든 next_*가 엔진 KeyError 없이 흘러야 함.
    엔진의 신호 evaluation 결과 자체는 본 테스트의 관심사가 아니며,
    smoke 수준에서 daily_equity가 채워지는지만 확인.
    """
    from app.backtest.config import BacktestConfig
    from app.backtest.engine import BacktestEngine
    from app.backtest.execution import ExecutionModel
    from app.portfolio.cash_manager import CashManager
    from app.portfolio.portfolio import Portfolio
    from app.strategy.engine import StrategyEngine

    selector = UniverseSelector(loaded_session)
    loader = PriceLoader(loaded_session)

    universe = selector.select(
        config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
        as_of_date=AS_OF_DATE,
    )
    target = universe[0]  # 000001 — symbol ASC 보장
    df = loader.load(target.symbol, LOAD_START, LOAD_END)
    assert len(df) >= 2, "엔진 smoke를 위해 최소 2 row 필요"

    # 신호 항상 False — 매수/매도 0건이지만 엔진은 끝까지 흘러야 함
    strategy = {
        "entry": {"logic": "AND", "conditions": []},
        "exit_signal": {"logic": "OR", "conditions": []},
        "exit_position": {"conditions": []},
        "filters": {"logic": "AND", "conditions": []},
    }
    portfolio = Portfolio(initial_cash=10_000_000)
    execution_model = ExecutionModel(fee_rate=0.00015, tax_rate=0.0018, slippage=0.0)
    config = BacktestConfig(
        symbol=target.symbol,
        start_date=LOAD_START,
        end_date=LOAD_END,
        position_size_amount=10_000_000,
        initial_cash=10_000_000,
    )
    cash_manager = CashManager(rule=None, execution_model=execution_model)
    strategy_engine = StrategyEngine(strategy_json=strategy)
    engine = BacktestEngine(
        config=config,
        portfolio=portfolio,
        execution_model=execution_model,
        strategy_engine=strategy_engine,
        cash_manager=cash_manager,
    )

    result = engine.run(df)
    # 015 정합: 모든 row에 대해 daily_equity 생성 (KeyError 없음)
    assert len(result.daily_equity) == len(df), (
        "PriceLoader DataFrame이 BacktestEngine 입력 명세와 불일치 — 015 회귀"
    )
    assert result.initial_cash == 10_000_000
