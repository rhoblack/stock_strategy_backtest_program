"""priority 알고리즘 + symbol_asc tie-breaker + random_seed 단위 테스트.

Phase 10 step 021 — 04-k / 13-n / 13-o (M7 잔존 해소).

검증 항목 (정확성 정책 13.17):
    - 동시 신호 우선순위 결정론
    - random_seed 동일 시 동일 결과
    - tie-breaker symbol_asc 결정론
    - look-ahead bias 차단 (today row만 사용)
"""

from datetime import date

import pandas as pd
import pytest

# 5개 기본 조건 자동 등록
import app.strategy  # noqa: F401
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

SYMBOL_A = "000001"
SYMBOL_B = "000002"
SYMBOL_C = "000003"


# ========================================================================
# 헬퍼
# ========================================================================


def _make_df(
    dates: list[date],
    closes: list[float],
    *,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
    market_caps: list[float] | None = None,
) -> pd.DataFrame:
    """단일 종목 시계열 DataFrame 생성. multi_symbol 헬퍼와 동일 + market_cap 옵션."""
    n = len(dates)
    if opens is None:
        opens = closes
    if highs is None:
        highs = [max(o, c) for o, c in zip(opens, closes, strict=True)]
    if lows is None:
        lows = [min(o, c) for o, c in zip(opens, closes, strict=True)]
    if volumes is None:
        volumes = [10_000.0] * n

    cols = {
        "date": dates,
        "adj_open": opens,
        "adj_high": highs,
        "adj_low": lows,
        "adj_close": closes,
        "adj_volume": volumes,
    }
    if market_caps is not None:
        cols["market_cap"] = market_caps
    df = pd.DataFrame(cols)
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    return df


def _trivial_entry_strategy() -> dict:
    """가격 > MA(2) entry."""
    return {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        }
    }


def _make_engine(
    *,
    strategy: dict,
    initial_cash: float = 1_000_000,
    position_size: float = 500_000,
    priority_method: str = "none",
    priority_tie_breaker: str = "symbol_asc",
    random_seed: int | None = None,
    symbol: str = SYMBOL_A,
):
    portfolio = Portfolio(initial_cash=initial_cash)
    execution_model = ExecutionModel(
        fee_rate=0.0,
        tax_rate=0.0,
        slippage=0.0,
        tick_rounding="nearest",
    )
    config = BacktestConfig(
        symbol=symbol,
        start_date=date(2024, 1, 1),
        end_date=date(2030, 12, 31),
        position_size_amount=position_size,
        initial_cash=initial_cash,
        priority_method=priority_method,
        priority_tie_breaker=priority_tie_breaker,
        random_seed=random_seed,
    )
    return BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)


# ========================================================================
# A) BacktestConfig 검증 — 화이트리스트 + random_seed 정책
# ========================================================================


def test_config_default_priority_method_is_none():
    """default priority_method='none' (020 호환)."""
    config = BacktestConfig(
        symbol=SYMBOL_A,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        position_size_amount=500_000,
        initial_cash=1_000_000,
    )
    assert config.priority_method == "none"
    assert config.priority_tie_breaker == "symbol_asc"
    assert config.random_seed is None


def test_config_unsupported_priority_method_raises():
    """화이트리스트 외 method는 ValueError."""
    with pytest.raises(ValueError, match="priority_method"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            priority_method="unknown_method",
        )


def test_config_unsupported_tie_breaker_raises():
    """화이트리스트 외 tie_breaker는 ValueError (현재는 symbol_asc만 지원)."""
    with pytest.raises(ValueError, match="tie_breaker"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            priority_tie_breaker="symbol_desc",
        )


def test_config_random_method_without_seed_raises():
    """priority_method='random' + random_seed=None → ValueError (CLAUDE.md #8)."""
    with pytest.raises(ValueError, match="random_seed"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            priority_method="random",
            random_seed=None,
        )


def test_config_random_method_with_seed_ok():
    """priority_method='random' + random_seed=int → 정상."""
    config = BacktestConfig(
        symbol=SYMBOL_A,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        position_size_amount=500_000,
        initial_cash=1_000_000,
        priority_method="random",
        random_seed=42,
    )
    assert config.priority_method == "random"
    assert config.random_seed == 42


# ========================================================================
# B) priority="none" 동작 — 020과 동일 (symbol ASC)
# ========================================================================


def test_priority_none_keeps_symbol_asc_order():
    """priority='none' 기본 → symbol ASC (020 회귀 보호)."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=1_000_000,
        position_size=500_000,
        priority_method="none",
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # cash 1_000_000 / 500_000 = 2종목 → symbol ASC로 A, B
    assert [b["symbol"] for b in buys] == [SYMBOL_A, SYMBOL_B]


# ========================================================================
# C) priority="trading_value_desc"
# ========================================================================


def test_priority_trading_value_desc_orders_by_close_times_volume():
    """trading_value_desc: today close × volume 내림차순. cash 부족 시 큰 종목부터."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day3(12) 신호일 close=110. volume으로 차등화.
    # A: close 110, vol 1_000 → 110_000
    # B: close 110, vol 5_000 → 550_000  (가장 큼)
    # C: close 110, vol 2_000 → 220_000
    df_a = _make_df(dates, closes=[100, 100, 110, 110], volumes=[10_000, 10_000, 1_000, 10_000])
    df_b = _make_df(dates, closes=[100, 100, 110, 110], volumes=[10_000, 10_000, 5_000, 10_000])
    df_c = _make_df(dates, closes=[100, 100, 110, 110], volumes=[10_000, 10_000, 2_000, 10_000])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=1_000_000,
        position_size=500_000,
        priority_method="trading_value_desc",
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # 정렬: B(550k), C(220k), A(110k) → cash로 B, C 매수, A skip
    assert [b["symbol"] for b in buys] == [SYMBOL_B, SYMBOL_C], [b["symbol"] for b in buys]


def test_priority_trading_value_desc_tie_breaker_symbol_asc():
    """trading_value 동점 시 symbol ASC tie-breaker."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # 모두 동일 trading_value → symbol ASC로 A, B만 매수, C skip
    df_a = _make_df(dates, closes=[100, 100, 110, 110], volumes=[10_000] * 4)
    df_b = _make_df(dates, closes=[100, 100, 110, 110], volumes=[10_000] * 4)
    df_c = _make_df(dates, closes=[100, 100, 110, 110], volumes=[10_000] * 4)

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=1_000_000,
        position_size=500_000,
        priority_method="trading_value_desc",
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert [b["symbol"] for b in buys] == [SYMBOL_A, SYMBOL_B]


# ========================================================================
# D) priority="market_cap_desc"
# ========================================================================


def test_priority_market_cap_desc_orders_by_market_cap():
    """market_cap_desc: today market_cap 내림차순."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day3(12) market_cap: A=1B, B=3B, C=2B → 정렬 B, C, A → cash 2종목분 → B, C
    df_a = _make_df(
        dates, closes=[100, 100, 110, 110],
        market_caps=[1e9, 1e9, 1e9, 1e9],
    )
    df_b = _make_df(
        dates, closes=[100, 100, 110, 110],
        market_caps=[3e9, 3e9, 3e9, 3e9],
    )
    df_c = _make_df(
        dates, closes=[100, 100, 110, 110],
        market_caps=[2e9, 2e9, 2e9, 2e9],
    )

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=1_000_000,
        position_size=500_000,
        priority_method="market_cap_desc",
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert [b["symbol"] for b in buys] == [SYMBOL_B, SYMBOL_C]


def test_priority_market_cap_desc_excludes_missing_market_cap():
    """market_cap 컬럼이 없거나 NaN인 후보는 매수 후보에서 제외."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # A: market_cap 컬럼 자체 없음 → 제외
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    # B: 정상
    df_b = _make_df(
        dates, closes=[100, 100, 110, 110],
        market_caps=[3e9, 3e9, 3e9, 3e9],
    )
    # C: market_cap 컬럼은 있지만 신호일 NaN → 제외
    df_c = _make_df(
        dates, closes=[100, 100, 110, 110],
        market_caps=[2e9, 2e9, float("nan"), 2e9],
    )

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=2_000_000,
        position_size=500_000,
        priority_method="market_cap_desc",
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # B만 매수 가능
    assert [b["symbol"] for b in buys] == [SYMBOL_B]


def test_priority_market_cap_desc_tie_breaker_symbol_asc():
    """market_cap 동점 → symbol ASC."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110], market_caps=[1e9] * 4)
    df_b = _make_df(dates, closes=[100, 100, 110, 110], market_caps=[1e9] * 4)
    df_c = _make_df(dates, closes=[100, 100, 110, 110], market_caps=[1e9] * 4)

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=1_000_000,
        position_size=500_000,
        priority_method="market_cap_desc",
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert [b["symbol"] for b in buys] == [SYMBOL_A, SYMBOL_B]


# ========================================================================
# E) priority="random" + random_seed
# ========================================================================


def test_priority_random_same_seed_same_result_5_runs():
    """동일 seed 5회 반복 → 모두 동일 매수 순서 (결정론, 정확성 정책 13.12.2)."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])

    bought_orders: list[list[str]] = []
    finals: list[float] = []
    for _ in range(5):
        engine = _make_engine(
            strategy=_trivial_entry_strategy(),
            initial_cash=1_000_000,  # 2종목분만
            position_size=500_000,
            priority_method="random",
            random_seed=42,
        )
        result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
        buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
        bought_orders.append([b["symbol"] for b in buys])
        finals.append(result.final_equity)

    assert all(o == bought_orders[0] for o in bought_orders), bought_orders
    assert all(f == finals[0] for f in finals), finals
    # cash로 2종목만 매수
    assert len(bought_orders[0]) == 2


def test_priority_random_different_seeds_can_yield_different_orders():
    """seed가 다르면 매수 순서가 달라질 수 있음 (몇 개 시드 중 하나는 달라야 함)."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])

    orders: dict[int, tuple[str, ...]] = {}
    for seed in (0, 1, 2, 3, 7, 42, 100):
        engine = _make_engine(
            strategy=_trivial_entry_strategy(),
            initial_cash=1_000_000,
            position_size=500_000,
            priority_method="random",
            random_seed=seed,
        )
        result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
        buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
        orders[seed] = tuple(b["symbol"] for b in buys)

    unique_orders = set(orders.values())
    # 7개 seed 중 적어도 2개 이상의 서로 다른 순서가 나와야 random이 실제로 동작.
    # 모두 같은 순서가 나오면 random이 사실상 dead-code.
    assert len(unique_orders) >= 2, orders


def test_priority_random_seed_zero_is_deterministic():
    """seed=0도 결정론 (truthy 체크 버그 방지)."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])

    finals: list[float] = []
    for _ in range(3):
        engine = _make_engine(
            strategy=_trivial_entry_strategy(),
            initial_cash=1_000_000,
            position_size=500_000,
            priority_method="random",
            random_seed=0,
        )
        result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
        finals.append(result.final_equity)

    assert all(f == finals[0] for f in finals), finals
