"""PositionSizer 단위·통합 테스트.

정확성 정책 13.17 매핑:
- 결정론 (13.12): sizing_method별 수량 계산 결과가 동일 입력에서 항상 동일 (state-free).
- 하위 호환 (CLAUDE.md #3): BacktestConfig default sizing_method="fixed_amount"
  + position_size_amount만 사용해도 기존 동작 유지.
- 모듈 책임 분리 (04번 §3): BacktestEngine이 PositionSizer.calculate_quantity를
  호출하는지 통합 확인.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import app.strategy  # noqa: F401 — 5개 기본 조건 자동 등록
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel
from app.portfolio.portfolio import Portfolio
from app.portfolio.sizer import PositionSizer
from app.strategy.engine import StrategyEngine

# ============================================================================
# 헬퍼
# ============================================================================


def _make_config(**kwargs) -> BacktestConfig:
    """기본 BacktestConfig 생성 헬퍼. 누락 필드는 default로 채움."""
    defaults = dict(
        symbol="TEST",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 3, 31),
        position_size_amount=1_000_000,
        initial_cash=10_000_000,
    )
    defaults.update(kwargs)
    return BacktestConfig(**defaults)


def _make_portfolio(cash: float = 10_000_000) -> Portfolio:
    return Portfolio(initial_cash=cash)


# ============================================================================
# 1. fixed_amount: 기본 케이스
# ============================================================================


def test_fixed_amount_basic():
    """TC-01: position_size_amount=1_000_000, exec_price=50_000 → quantity=20."""
    sizer = PositionSizer()
    config = _make_config(position_size_amount=1_000_000, sizing_method="fixed_amount")
    portfolio = _make_portfolio()

    qty = sizer.calculate_quantity(50_000, portfolio, config)
    assert qty == 20  # int(1_000_000 // 50_000) = 20


# ============================================================================
# 2. fixed_amount: exec_price > position_size_amount → quantity=0
# ============================================================================


def test_fixed_amount_price_exceeds_amount():
    """TC-02: exec_price=1_100_000 > position_size_amount=1_000_000 → quantity=0."""
    sizer = PositionSizer()
    config = _make_config(position_size_amount=1_000_000, sizing_method="fixed_amount")
    portfolio = _make_portfolio()

    qty = sizer.calculate_quantity(1_100_000, portfolio, config)
    assert qty == 0  # int(1_000_000 // 1_100_000) = 0


# ============================================================================
# 3. fixed_ratio: total_equity × ratio → 금액 → 수량
# ============================================================================


def test_fixed_ratio_basic():
    """TC-03: total_equity=10_000_000, ratio=0.1, exec_price=50_000 → quantity=20."""
    sizer = PositionSizer()
    config = _make_config(
        sizing_method="fixed_ratio",
        sizing_ratio=0.1,
    )
    portfolio = _make_portfolio(cash=10_000_000)
    # total_equity = 10_000_000 (보유 종목 없음)
    # amount = 10_000_000 × 0.1 = 1_000_000
    # qty = int(1_000_000 // 50_000) = 20

    qty = sizer.calculate_quantity(50_000, portfolio, config)
    assert qty == 20


# ============================================================================
# 4. fixed_ratio: sizing_ratio=None이면 ValueError
# ============================================================================


def test_fixed_ratio_requires_sizing_ratio():
    """TC-04: sizing_method='fixed_ratio', sizing_ratio=None → BacktestConfig에서 ValueError."""
    with pytest.raises(ValueError, match="sizing_ratio"):
        _make_config(sizing_method="fixed_ratio", sizing_ratio=None)


# ============================================================================
# 5. equal_weight: total_equity / max_positions → 수량
# ============================================================================


def test_equal_weight_basic():
    """TC-05: total_equity=10_000_000, max_positions=5, exec_price=50_000 → quantity=40."""
    sizer = PositionSizer()
    config = _make_config(
        sizing_method="equal_weight",
        max_positions=5,
    )
    portfolio = _make_portfolio(cash=10_000_000)
    # amount = 10_000_000 / 5 = 2_000_000
    # qty = int(2_000_000 // 50_000) = 40

    qty = sizer.calculate_quantity(50_000, portfolio, config)
    assert qty == 40


# ============================================================================
# 6. equal_weight: max_positions=None → ValueError
# ============================================================================


def test_equal_weight_requires_max_positions():
    """TC-06: sizing_method='equal_weight', max_positions=None → PositionSizer.calculate_quantity에서 ValueError."""
    sizer = PositionSizer()
    config = _make_config(sizing_method="equal_weight", max_positions=None)
    portfolio = _make_portfolio()

    with pytest.raises(ValueError, match="max_positions"):
        sizer.calculate_quantity(50_000, portfolio, config)


# ============================================================================
# 7. 지원하지 않는 sizing_method → ValueError
# ============================================================================


def test_unsupported_sizing_method_in_config():
    """TC-07: 지원하지 않는 sizing_method → BacktestConfig에서 ValueError."""
    with pytest.raises(ValueError, match="sizing_method"):
        _make_config(sizing_method="kelly_criterion")


# ============================================================================
# 8. exec_price=0 → quantity=0 (제로 나눗셈 방지)
# ============================================================================


def test_exec_price_zero_returns_zero():
    """TC-08: exec_price=0 → 제로 나눗셈 없이 0 반환."""
    sizer = PositionSizer()
    config = _make_config(sizing_method="fixed_amount", position_size_amount=1_000_000)
    portfolio = _make_portfolio()

    qty = sizer.calculate_quantity(0, portfolio, config)
    assert qty == 0


# ============================================================================
# 9. fixed_ratio: exec_price > amount → quantity=0
# ============================================================================


def test_fixed_ratio_price_exceeds_amount():
    """TC-09: ratio=0.01 → amount=100_000, exec_price=200_000 → quantity=0."""
    sizer = PositionSizer()
    config = _make_config(sizing_method="fixed_ratio", sizing_ratio=0.01)
    portfolio = _make_portfolio(cash=10_000_000)
    # amount = 10_000_000 × 0.01 = 100_000
    # qty = int(100_000 // 200_000) = 0

    qty = sizer.calculate_quantity(200_000, portfolio, config)
    assert qty == 0


# ============================================================================
# 10. BacktestConfig: default sizing_method="fixed_amount" (하위 호환)
# ============================================================================


def test_backtest_config_default_sizing_method():
    """TC-10: sizing_method 지정 없으면 default='fixed_amount' (하위 호환)."""
    config = BacktestConfig(
        symbol="TEST",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 3, 31),
        position_size_amount=1_000_000,
        initial_cash=10_000_000,
    )
    assert config.sizing_method == "fixed_amount"
    assert config.sizing_ratio is None


# ============================================================================
# 11. BacktestConfig: sizing_method='fixed_ratio', sizing_ratio=None → ValueError
# ============================================================================


def test_backtest_config_fixed_ratio_missing_ratio_raises():
    """TC-11: BacktestConfig에서 fixed_ratio + sizing_ratio=None → ValueError."""
    with pytest.raises(ValueError, match="sizing_ratio"):
        BacktestConfig(
            symbol="TEST",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 3, 31),
            position_size_amount=1_000_000,
            initial_cash=10_000_000,
            sizing_method="fixed_ratio",
            sizing_ratio=None,
        )


# ============================================================================
# 12. BacktestConfig: sizing_ratio 범위 검증
# ============================================================================


def test_backtest_config_sizing_ratio_out_of_range():
    """TC-12: sizing_ratio > 1 또는 <= 0 → ValueError."""
    with pytest.raises(ValueError, match="sizing_ratio"):
        _make_config(sizing_method="fixed_ratio", sizing_ratio=1.5)

    with pytest.raises(ValueError, match="sizing_ratio"):
        _make_config(sizing_method="fixed_ratio", sizing_ratio=0.0)

    with pytest.raises(ValueError, match="sizing_ratio"):
        _make_config(sizing_method="fixed_ratio", sizing_ratio=-0.1)


# ============================================================================
# 13. BacktestEngine 통합: PositionSizer를 통해 수량 계산 (fixed_amount 하위 호환)
# ============================================================================


def _build_simple_series(n: int = 30) -> pd.DataFrame:
    """단순 합성 시계열 (고정 가격, 상승 추세로 entry 조건 충족 보장)."""
    # 일정하게 상승하는 close 시계열
    closes = 10_000 + np.arange(n) * 100  # 10000, 10100, ..., 12900
    highs = closes + 200
    lows = closes - 200
    opens = closes - 50

    base_date = date(2024, 1, 2)
    dates = [base_date + timedelta(days=i) for i in range(n)]

    df = pd.DataFrame(
        {
            "date": dates,
            "adj_open": opens.astype(float),
            "adj_high": highs.astype(float),
            "adj_low": lows.astype(float),
            "adj_close": closes.astype(float),
            "adj_volume": np.full(n, 10_000.0),
        }
    )
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    return df


def test_backtest_engine_uses_position_sizer_fixed_amount():
    """TC-13a: fixed_amount (default) → BacktestEngine이 PositionSizer를 거쳐 동일 수량 계산.

    position_size_amount=1_000_000, exec_price ≈ 10_050
    → quantity = int(1_000_000 // ~10_050) ≈ 99
    거래가 발생하면 trade_logs에 기록됨.
    """
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
        },
    }
    df = _build_simple_series(30)
    portfolio = Portfolio(initial_cash=10_000_000)
    execution_model = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    config = BacktestConfig(
        symbol="TEST",
        start_date=df["date"].iloc[0],
        end_date=df["date"].iloc[-1],
        position_size_amount=1_000_000,
        initial_cash=10_000_000,
        sizing_method="fixed_amount",
    )
    engine = BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)
    assert hasattr(engine, "position_sizer"), "BacktestEngine이 position_sizer를 갖고 있어야 함"

    engine.run(df)
    # 상승 추세 → entry 발생 확인 (trade_logs에 BUY 존재)
    buy_logs = [t for t in portfolio.trade_logs if t.get("side") == "buy"]
    assert len(buy_logs) >= 1, "상승 추세에서 최소 1회 매수가 발생해야 함"

    # 첫 매수 수량이 position_size_amount // exec_price와 일치하는지 확인
    first_buy = buy_logs[0]
    exec_price = first_buy["price"]
    expected_qty = int(1_000_000 // exec_price)
    assert first_buy["quantity"] == expected_qty


def test_backtest_engine_uses_position_sizer_fixed_ratio():
    """TC-13b: fixed_ratio → BacktestEngine이 PositionSizer를 통해 total_equity 기반 수량 계산."""
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
        },
    }
    df = _build_simple_series(30)
    portfolio = Portfolio(initial_cash=10_000_000)
    execution_model = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    config = BacktestConfig(
        symbol="TEST",
        start_date=df["date"].iloc[0],
        end_date=df["date"].iloc[-1],
        position_size_amount=1_000_000,  # fixed_ratio에서는 무시되지만 필수 필드
        initial_cash=10_000_000,
        sizing_method="fixed_ratio",
        sizing_ratio=0.1,  # 총자산 10%
    )
    engine = BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)
    engine.run(df)

    buy_logs = [t for t in portfolio.trade_logs if t.get("side") == "buy"]
    assert len(buy_logs) >= 1, "상승 추세에서 최소 1회 매수가 발생해야 함"

    # 첫 매수는 initial_cash(=total_equity) × 0.1 / exec_price
    first_buy = buy_logs[0]
    exec_price = first_buy["price"]
    expected_qty = int(10_000_000 * 0.1 // exec_price)
    assert first_buy["quantity"] == expected_qty


def test_backtest_engine_uses_position_sizer_equal_weight():
    """TC-13c: equal_weight → BacktestEngine이 PositionSizer를 통해 총자산/max_positions 기반 수량 계산."""
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
        },
    }
    df = _build_simple_series(30)
    portfolio = Portfolio(initial_cash=10_000_000)
    execution_model = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    config = BacktestConfig(
        symbol="TEST",
        start_date=df["date"].iloc[0],
        end_date=df["date"].iloc[-1],
        position_size_amount=1_000_000,  # equal_weight에서는 무시되지만 필수 필드
        initial_cash=10_000_000,
        sizing_method="equal_weight",
        max_positions=5,
    )
    engine = BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)
    engine.run(df)

    buy_logs = [t for t in portfolio.trade_logs if t.get("side") == "buy"]
    assert len(buy_logs) >= 1, "상승 추세에서 최소 1회 매수가 발생해야 함"

    # 첫 매수는 initial_cash / max_positions / exec_price
    first_buy = buy_logs[0]
    exec_price = first_buy["price"]
    expected_qty = int(10_000_000 / 5 // exec_price)
    assert first_buy["quantity"] == expected_qty


# ============================================================================
# 14. 결정론: 동일 입력 → 동일 수량 (state-free 확인)
# ============================================================================


def test_position_sizer_is_deterministic():
    """TC-14: 동일 입력에서 여러 번 호출해도 항상 동일 수량 반환 (결정론, 13.12)."""
    sizer = PositionSizer()
    config = _make_config(sizing_method="fixed_ratio", sizing_ratio=0.15)
    portfolio = _make_portfolio(cash=8_000_000)

    results = [sizer.calculate_quantity(50_000, portfolio, config) for _ in range(5)]
    assert len(set(results)) == 1, f"결정론 위반: {results}"
    # 8_000_000 × 0.15 = 1_200_000 / 50_000 = 24
    assert results[0] == 24


# ============================================================================
# 15. exec_price 음수 → 0 반환 (방어 코드)
# ============================================================================


def test_exec_price_negative_returns_zero():
    """TC-15: exec_price < 0 → 0 반환 (제로 나눗셈 방지와 동일 경로)."""
    sizer = PositionSizer()
    config = _make_config(sizing_method="fixed_amount", position_size_amount=1_000_000)
    portfolio = _make_portfolio()

    qty = sizer.calculate_quantity(-1000, portfolio, config)
    assert qty == 0


# ============================================================================
# 16. sizing_ratio 경계값: 1.0은 허용, 1.0 초과는 거부
# ============================================================================


def test_sizing_ratio_boundary():
    """TC-16: sizing_ratio=1.0은 허용(100% 투자), >1.0은 ValueError."""
    # 1.0은 허용 (총자산 100%)
    config = _make_config(sizing_method="fixed_ratio", sizing_ratio=1.0)
    assert config.sizing_ratio == 1.0

    # 1.0 초과 거부
    with pytest.raises(ValueError, match="sizing_ratio"):
        _make_config(sizing_method="fixed_ratio", sizing_ratio=1.01)
