"""Golden test — 파일 기반 fixtures/strategies/expected 구조 검증.

12번 §15.2 구조:
  golden/fixtures/   — 시세 데이터 파일 (합성 데이터는 conftest.build_synthetic_series)
  golden/strategies/ — 전략 JSON 파일
  golden/expected/   — 기대값 JSON 파일

이 파일은 파일 기반 golden test 구조를 검증합니다.
Phase 1 golden 핵심 회귀 검증은 integration/test_phase1_golden.py에서 유지됩니다.
(기존 회귀 보증 파일은 그대로 유지 — 이 파일은 파일 기반 구조를 추가 보강)
"""

import pytest

# 5개 기본 조건 자동 등록
import app.strategy  # noqa: F401
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel
from app.backtest.metrics import calculate_metrics
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

from .conftest import build_synthetic_series, load_expected, load_strategy

# ============================================================================
# 헬퍼
# ============================================================================


def _run(
    strategy: dict,
    df,
    *,
    initial_cash: float = 10_000_000,
    position_size_amount: float = 5_000_000,
    fee_rate: float = 0.0,
    tax_rate: float = 0.0,
    slippage: float = 0.0,
    tick_rounding: str = "nearest",
):
    portfolio = Portfolio(initial_cash=initial_cash)
    execution_model = ExecutionModel(
        fee_rate=fee_rate,
        tax_rate=tax_rate,
        slippage=slippage,
        tick_rounding=tick_rounding,
    )
    config = BacktestConfig(
        symbol="GOLDEN",
        start_date=df["date"].iloc[0],
        end_date=df["date"].iloc[-1],
        position_size_amount=position_size_amount,
        initial_cash=initial_cash,
    )
    engine = BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)
    result = engine.run(df)
    metrics = calculate_metrics(result)
    return result, metrics


# ============================================================================
# golden_01: 파일 기반 전략 JSON + 기대값 JSON 검증
# ============================================================================


def test_golden_01_file_based_strategy_matches_expected():
    """golden_01 전략 JSON 파일과 기대값 JSON 파일로 회귀 검증.

    파일 기반 구조: golden/strategies/golden_01_ma_cross.json
                   golden/expected/golden_01_summary.json

    실제 백테스트 결과가 expected 값과 일치해야 함.
    (integration/test_phase1_golden.py와 동일한 결과를 검증하는 파일 기반 중복 보증)
    """

    strategy = load_strategy("golden_01_ma_cross")
    expected = load_expected("golden_01_summary")
    df = build_synthetic_series(seed=42, n=90)

    result, metrics = _run(strategy, df)

    # summary 검증
    assert metrics["initial_cash"] == expected["initial_cash"]
    assert metrics["final_equity"] == pytest.approx(expected["final_equity"], abs=1.0)
    assert metrics["total_return_pct"] == pytest.approx(expected["total_return_pct"], abs=0.001)
    assert metrics["mdd_pct"] == pytest.approx(expected["mdd_pct"], abs=0.01)
    assert metrics["trade_count"] == expected["trade_count"]
    assert metrics["open_position_count"] == expected["open_position_count"]
    assert metrics["win_rate"] == pytest.approx(expected["win_rate"], abs=0.01)
    assert metrics["avg_holding_days"] == pytest.approx(expected["avg_holding_days"], abs=0.01)
    assert metrics["profit_factor"] == pytest.approx(expected["profit_factor"], abs=0.001)

    # daily_equity 길이
    assert len(result.daily_equity) == expected["daily_equity_length"]

    # 첫 거래 검증
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]

    assert len(buys) == expected["total_buy_count"]
    assert len(sells) == expected["total_sell_count"]

    first_buy = buys[0]
    assert first_buy["price"] == expected["first_buy_price"]
    assert str(first_buy["date"]) == expected["first_buy_date"]
    assert str(first_buy["signal_date"]) == expected["first_buy_signal_date"]


def test_golden_01_strategy_file_loads_correctly():
    """golden_01_ma_cross.json 파일 구조 검증 (StrategyEngine이 파싱할 수 있어야 함)."""
    strategy = load_strategy("golden_01_ma_cross")

    assert "entry" in strategy
    assert "exit_position" in strategy
    assert strategy["entry"]["logic"] == "AND"

    entry_conds = strategy["entry"]["conditions"]
    assert len(entry_conds) == 1
    assert entry_conds[0]["type"] == "price_vs_ma"
    assert entry_conds[0]["ma_period"] == 5

    exit_conds = strategy["exit_position"]["conditions"]
    assert len(exit_conds) == 2
    types = {c["type"] for c in exit_conds}
    assert types == {"take_profit", "stop_loss"}


def test_golden_02_strategy_file_loads_correctly():
    """golden_02_exit_signal_ma.json 파일 구조 검증."""
    strategy = load_strategy("golden_02_exit_signal_ma")

    assert "entry" in strategy
    assert "exit_signal" in strategy
    assert "exit_position" not in strategy

    assert strategy["exit_signal"]["conditions"][0]["type"] == "price_vs_ma"
    assert strategy["exit_signal"]["conditions"][0]["operator"] == "<"


def test_golden_03_strategy_file_loads_correctly():
    """golden_03_rsi_multi_condition.json 파일 구조 검증."""
    strategy = load_strategy("golden_03_rsi_multi_condition")

    assert "entry" in strategy
    assert "exit_position" in strategy

    entry_conds = strategy["entry"]["conditions"]
    assert len(entry_conds) == 2
    entry_types = {c["type"] for c in entry_conds}
    assert entry_types == {"price_vs_ma", "rsi_level"}

    exit_conds = strategy["exit_position"]["conditions"]
    exit_types = {c["type"] for c in exit_conds}
    assert exit_types == {"take_profit", "stop_loss", "max_holding_days"}


# ============================================================================
# 파일 기반 golden test 구조 무결성 검증
# ============================================================================


def test_golden_directory_structure_exists():
    """golden test 디렉토리 구조가 올바르게 설정됐는지 확인.

    12번 §15.2 구조 검증.
    """
    from pathlib import Path

    golden_dir = Path(__file__).parent
    assert (golden_dir / "strategies").exists(), "strategies 디렉토리 없음"
    assert (golden_dir / "expected").exists(), "expected 디렉토리 없음"
    assert (golden_dir / "fixtures").exists(), "fixtures 디렉토리 없음"

    # 최소 전략 파일 존재
    strategy_files = list((golden_dir / "strategies").glob("*.json"))
    assert len(strategy_files) >= 3, f"golden strategy JSON이 3개 이상이어야 함: {strategy_files}"

    # 최소 기대값 파일 존재
    expected_files = list((golden_dir / "expected").glob("*.json"))
    assert len(expected_files) >= 1, f"golden expected JSON이 1개 이상이어야 함: {expected_files}"
