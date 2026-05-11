"""step 064 - priority 3종 엔진 구현 테스트 (02-s).

market_cap_asc / volume_ratio_desc / price_change_desc 정렬 알고리즘 +
symbol_asc tie-breaker + 결정론 검증.
"""

from datetime import date

import pandas as pd

import app.strategy  # noqa: F401
from app.backtest.config import SUPPORTED_PRIORITY_METHODS, BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

SYMBOL_A = "000001"
SYMBOL_B = "000002"
SYMBOL_C = "000003"


def _make_engine(priority_method: str, symbol: str = SYMBOL_A) -> BacktestEngine:
    config = BacktestConfig(
        symbol=symbol,
        start_date=date(2024, 1, 1),
        end_date=date(2030, 12, 31),
        position_size_amount=100_000,
        initial_cash=10_000_000,
        priority_method=priority_method,
    )
    portfolio = Portfolio(initial_cash=10_000_000)
    execution_model = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    strategy = {"entry": {"logic": "AND", "conditions": []}}
    return BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)


def _row(symbol: str, **kwargs) -> tuple[str, pd.Series]:
    base = {
        "adj_open": 1000.0,
        "adj_high": 1100.0,
        "adj_low": 900.0,
        "adj_close": 1000.0,
        "adj_volume": 10_000.0,
        "prev_close": 1000.0,
    }
    base.update(kwargs)
    return symbol, pd.Series(base)


# ========================================================================
# SUPPORTED_PRIORITY_METHODS
# ========================================================================


def test_new_methods_in_supported():
    assert "market_cap_asc" in SUPPORTED_PRIORITY_METHODS
    assert "volume_ratio_desc" in SUPPORTED_PRIORITY_METHODS
    assert "price_change_desc" in SUPPORTED_PRIORITY_METHODS


def test_config_accepts_new_methods():
    for method in ["market_cap_asc", "volume_ratio_desc", "price_change_desc"]:
        cfg = BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=100_000,
            initial_cash=1_000_000,
            priority_method=method,
        )
        assert cfg.priority_method == method


# ========================================================================
# market_cap_asc
# ========================================================================


def test_market_cap_asc_sorts_ascending():
    engine = _make_engine("market_cap_asc")
    candidates = [
        _row(SYMBOL_A, market_cap=500_000_000),
        _row(SYMBOL_B, market_cap=100_000_000),
        _row(SYMBOL_C, market_cap=200_000_000),
    ]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_B, SYMBOL_C, SYMBOL_A]


def test_market_cap_asc_tie_breaker():
    engine = _make_engine("market_cap_asc")
    candidates = [
        _row(SYMBOL_C, market_cap=100_000_000),
        _row(SYMBOL_A, market_cap=100_000_000),
        _row(SYMBOL_B, market_cap=100_000_000),
    ]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_A, SYMBOL_B, SYMBOL_C]


def test_market_cap_asc_nan_excluded():
    engine = _make_engine("market_cap_asc")
    candidates = [
        _row(SYMBOL_A, market_cap=float("nan")),
        _row(SYMBOL_B, market_cap=100_000_000),
    ]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_B]


def test_market_cap_asc_missing_column_excluded():
    engine = _make_engine("market_cap_asc")
    row_a = pd.Series({"adj_close": 1000.0, "adj_volume": 10_000.0})
    candidates = [(SYMBOL_A, row_a), _row(SYMBOL_B, market_cap=100_000_000)]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_B]


# ========================================================================
# volume_ratio_desc
# ========================================================================


def test_volume_ratio_desc_with_avg_volume():
    engine = _make_engine("volume_ratio_desc")
    candidates = [
        _row(SYMBOL_A, adj_volume=10_000, avg_volume=5_000),
        _row(SYMBOL_B, adj_volume=50_000, avg_volume=10_000),
        _row(SYMBOL_C, adj_volume=3_000, avg_volume=3_000),
    ]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_B, SYMBOL_A, SYMBOL_C]


def test_volume_ratio_desc_with_volume_ratio_column():
    engine = _make_engine("volume_ratio_desc")
    candidates = [
        _row(SYMBOL_A, volume_ratio=1.5),
        _row(SYMBOL_B, volume_ratio=3.0),
        _row(SYMBOL_C, volume_ratio=0.8),
    ]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_B, SYMBOL_A, SYMBOL_C]


def test_volume_ratio_desc_fallback_no_avg_volume():
    """avg_volume / volume_ratio 컬럼 없으면 adj_volume 자체로 정렬 (fallback)."""
    engine = _make_engine("volume_ratio_desc")
    candidates = [
        _row(SYMBOL_A, adj_volume=1_000),
        _row(SYMBOL_B, adj_volume=5_000),
        _row(SYMBOL_C, adj_volume=3_000),
    ]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_B, SYMBOL_C, SYMBOL_A]


def test_volume_ratio_desc_zero_volume_excluded():
    engine = _make_engine("volume_ratio_desc")
    candidates = [
        _row(SYMBOL_A, adj_volume=0),
        _row(SYMBOL_B, adj_volume=5_000),
    ]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_B]


def test_volume_ratio_desc_tie_breaker():
    engine = _make_engine("volume_ratio_desc")
    candidates = [
        _row(SYMBOL_C, adj_volume=5_000, avg_volume=1_000),
        _row(SYMBOL_A, adj_volume=5_000, avg_volume=1_000),
        _row(SYMBOL_B, adj_volume=5_000, avg_volume=1_000),
    ]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_A, SYMBOL_B, SYMBOL_C]


# ========================================================================
# price_change_desc
# ========================================================================


def test_price_change_desc_sorts_descending():
    engine = _make_engine("price_change_desc")
    candidates = [
        _row(SYMBOL_A, adj_close=1050, prev_close=1000),
        _row(SYMBOL_B, adj_close=1100, prev_close=1000),
        _row(SYMBOL_C, adj_close=1020, prev_close=1000),
    ]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_B, SYMBOL_A, SYMBOL_C]


def test_price_change_desc_negative_change():
    engine = _make_engine("price_change_desc")
    candidates = [
        _row(SYMBOL_A, adj_close=950, prev_close=1000),
        _row(SYMBOL_B, adj_close=1020, prev_close=1000),
        _row(SYMBOL_C, adj_close=980, prev_close=1000),
    ]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_B, SYMBOL_C, SYMBOL_A]


def test_price_change_desc_zero_prev_close_excluded():
    engine = _make_engine("price_change_desc")
    candidates = [
        _row(SYMBOL_A, adj_close=1000, prev_close=0),
        _row(SYMBOL_B, adj_close=1050, prev_close=1000),
    ]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_B]


def test_price_change_desc_no_prev_close_excluded():
    engine = _make_engine("price_change_desc")
    row_a = pd.Series({"adj_close": 1000.0, "adj_volume": 10_000.0})
    candidates = [(SYMBOL_A, row_a), _row(SYMBOL_B, adj_close=1050, prev_close=1000)]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_B]


def test_price_change_desc_tie_breaker():
    engine = _make_engine("price_change_desc")
    candidates = [
        _row(SYMBOL_C, adj_close=1050, prev_close=1000),
        _row(SYMBOL_A, adj_close=1050, prev_close=1000),
        _row(SYMBOL_B, adj_close=1050, prev_close=1000),
    ]
    result = engine._apply_priority(candidates)
    symbols = [s for s, _ in result]
    assert symbols == [SYMBOL_A, SYMBOL_B, SYMBOL_C]


# ========================================================================
# determinism
# ========================================================================


def test_determinism_all_new_methods():
    """3종 method 모두 동일 입력 5회 반복 동일 결과."""
    candidates = [
        _row(
            SYMBOL_A,
            market_cap=300_000_000,
            adj_volume=3_000,
            avg_volume=1_000,
            adj_close=1050,
            prev_close=1000,
        ),
        _row(
            SYMBOL_B,
            market_cap=100_000_000,
            adj_volume=5_000,
            avg_volume=1_000,
            adj_close=1100,
            prev_close=1000,
        ),
        _row(
            SYMBOL_C,
            market_cap=200_000_000,
            adj_volume=2_000,
            avg_volume=1_000,
            adj_close=1020,
            prev_close=1000,
        ),
    ]
    for method in ["market_cap_asc", "volume_ratio_desc", "price_change_desc"]:
        engine = _make_engine(method)
        results = []
        for _ in range(5):
            r = engine._apply_priority(candidates)
            results.append([s for s, _ in r])
        for r in results:
            assert r == results[0], f"method={method} 결정론 실패"
