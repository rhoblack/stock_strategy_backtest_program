"""Phase 1 Golden Test — 회귀 보증.

설계서 12번 15절. 고정된 시세 + 고정된 전략 → 고정된 결과를
박아두고 매 빌드마다 회귀 검증. 의도 변경 시 expected 갱신.

부동소수 비교는 절대 1원 또는 1e-6 상대 오차 허용.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

# 5개 기본 조건 자동 등록
import app.strategy  # noqa: F401
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel
from app.backtest.metrics import calculate_metrics
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

# ============================================================================
# 헬퍼
# ============================================================================


def _build_synthetic_series(seed: int, n: int, start_price: float = 10_000) -> pd.DataFrame:
    """결정론적 합성 가격 시계열. random_state 고정.

    OHLC는 close 기준으로 ±1% 범위. 거래량은 일정.
    """
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.001, scale=0.02, size=n)
    closes = start_price * np.exp(np.cumsum(returns))
    closes = closes.round(0)

    high_mults = 1 + rng.uniform(0.001, 0.015, n)
    low_mults = 1 - rng.uniform(0.001, 0.015, n)
    open_jitter = rng.uniform(-0.005, 0.005, n)

    opens = (closes * (1 + open_jitter)).round(0)
    highs = (np.maximum(closes, opens) * high_mults).round(0)
    lows = (np.minimum(closes, opens) * low_mults).round(0)

    base_date = date(2024, 1, 2)
    dates = [base_date + timedelta(days=i) for i in range(n)]

    df = pd.DataFrame(
        {
            "date": dates,
            "adj_open": opens,
            "adj_high": highs,
            "adj_low": lows,
            "adj_close": closes,
            "adj_volume": np.full(n, 10_000.0),
        }
    )
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    return df


def _run(
    strategy: dict,
    df: pd.DataFrame,
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
# golden_01: MA cross + take_profit/stop_loss
# ============================================================================


_GOLDEN_01_STRATEGY = {
    "entry": {
        "logic": "AND",
        "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
    },
    "exit_position": {
        "logic": "OR",
        "conditions": [
            {"type": "take_profit", "percent": 5.0, "trigger": "intraday_high"},
            {"type": "stop_loss", "percent": 3.0},
        ],
    },
}


def test_golden_01_ma_cross_take_profit_stop_loss():
    """단일 종목 90일, MA(5) entry, take=5% / stop=3% (비용 0).

    seed=42로 합성 데이터 생성. 1차 실행으로 산출한 정확한 결과를 박아둠.
    값이 깨지면 어딘가 의도하지 않은 변경 발생 — 정확성 정책 또는 계산식 회귀.
    """
    df = _build_synthetic_series(seed=42, n=90)
    result, metrics = _run(_GOLDEN_01_STRATEGY, df)

    # === Frozen expected (1차 실행 후 고정 / 015에서 avg_holding_days 갱신) ===
    # 015 (signal_date vs execution_date 분리) 영향:
    #   - final_equity / total_return / mdd / trade_count / win_rate / profit_factor:
    #     체결가는 그대로 next_open이라 자산 차이 없음 → 변경 없음.
    #   - avg_holding_days: 7.5 → 6.5
    #     entry는 next_open(=다음 거래일) 체결이라 entry_date가 1일 미뤄지지만,
    #     exit_position(intraday take/stop)은 당일 체결이라 exit_date는 그대로.
    #     실제 보유일수가 1일 줄어드는 게 정합 — CLAUDE.md look-ahead 체크리스트
    #     마지막 줄("신호일 종가로 신호, 다음날 시가로 체결") 의미 그대로.
    assert metrics["initial_cash"] == 10_000_000.0
    assert metrics["final_equity"] == pytest.approx(10_188_570.0, abs=1.0)
    assert metrics["total_return_pct"] == pytest.approx(1.8857, abs=0.001)
    assert metrics["mdd_pct"] == pytest.approx(-4.9032, abs=0.01)
    assert metrics["trade_count"] == 8
    assert metrics["open_position_count"] == 1
    assert metrics["win_rate"] == pytest.approx(37.5, abs=0.01)
    assert metrics["avg_holding_days"] == pytest.approx(6.5, abs=0.01)
    assert metrics["profit_factor"] == pytest.approx(1.2252, abs=0.001)

    # daily_equity 길이
    assert len(result.daily_equity) == 90


def test_golden_01_specific_first_trade_match():
    """첫 거래 매수 가격과 날짜가 정확히 예측 가능."""
    df = _build_synthetic_series(seed=42, n=90)
    result, _ = _run(_GOLDEN_01_STRATEGY, df)

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]

    assert len(buys) == 9
    assert len(sells) == 8

    first_buy = buys[0]
    # 015: first_buy["date"]는 execution_date (체결일).
    #   이전: 2024-01-12 (signal_date를 잘못 기록).
    #   이후: 2024-01-13 (next_date = 다음 거래일 시가 체결).
    # 가격 9_760은 2024-01-13의 시가로 변경 없음.
    assert first_buy["price"] == 9_760
    assert first_buy["date"] == date(2024, 1, 13)
    assert first_buy["execution_date"] == date(2024, 1, 13)
    assert first_buy["signal_date"] == date(2024, 1, 12)


def test_golden_01_determinism_two_runs():
    """golden_01을 두 번 실행해도 모든 값이 정확히 일치."""
    df = _build_synthetic_series(seed=42, n=90)
    _, m1 = _run(_GOLDEN_01_STRATEGY, df)
    _, m2 = _run(_GOLDEN_01_STRATEGY, df)
    assert m1 == m2  # dict 전체 비교


# ============================================================================
# golden_02: exit_signal (지표 매도만)
# ============================================================================


def test_golden_02_exit_signal_only_no_intraday():
    """price > MA(5) entry, price < MA(5) exit_signal.
    take_profit/stop_loss 없음 — 지표 매도만.
    """
    df = _build_synthetic_series(seed=7, n=60)
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
        },
        "exit_signal": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": "<"}],
        },
    }
    result, metrics = _run(strategy, df)

    # 지표 매도만 → 모든 청산이 exit_signal reason
    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    if sells:  # 거래가 있다면
        assert all(s["reason"] == "exit_signal" for s in sells), (
            f"지표 매도만이어야 하는데 다른 reason: {set(s['reason'] for s in sells)}"
        )

    # 결정론
    result2, metrics2 = _run(strategy, df)
    assert metrics["final_equity"] == metrics2["final_equity"]


# ============================================================================
# golden_03: 결정론 강한 검증 (10회 반복)
# ============================================================================


def test_golden_03_full_determinism_10_runs():
    """같은 입력 10회 반복 → 모든 지표가 정확히 일치."""
    df = _build_synthetic_series(seed=123, n=120)
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 5, "operator": ">"},
                {"type": "rsi_level", "period": 14, "operator": "<=", "value": 70},
            ],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [
                {"type": "take_profit", "percent": 7.0},
                {"type": "stop_loss", "percent": 3.0},
                {"type": "max_holding_days", "days": 10},
            ],
        },
    }

    results = []
    for _ in range(10):
        _, metrics = _run(strategy, df, fee_rate=0.00015, tax_rate=0.0018, slippage=0.001)
        results.append(metrics)

    # 첫 결과를 기준으로 모든 결과가 동일해야 함
    base = results[0]
    for i, m in enumerate(results[1:], start=2):
        assert m["final_equity"] == base["final_equity"], f"run #{i} final_equity 불일치"
        assert m["total_return_pct"] == pytest.approx(base["total_return_pct"]), f"run #{i}"
        assert m["mdd_pct"] == base["mdd_pct"], f"run #{i} mdd 불일치"
        assert m["trade_count"] == base["trade_count"], f"run #{i} trade_count 불일치"
        assert m["win_rate"] == base["win_rate"], f"run #{i} win_rate 불일치"
        assert m["avg_holding_days"] == base["avg_holding_days"], f"run #{i}"


# ============================================================================
# golden_04: 비용(수수료/세금/슬리피지) 적용 시나리오
# ============================================================================


def test_golden_04_with_realistic_costs():
    """실전 한국 주식 비용 적용: 수수료 0.015%, 거래세 0.18%, 슬리피지 0.1%.

    비용 0 시나리오 대비 final_equity가 더 낮아야 함.
    """
    df = _build_synthetic_series(seed=42, n=90)
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [
                {"type": "take_profit", "percent": 5.0},
                {"type": "stop_loss", "percent": 3.0},
            ],
        },
    }
    _, metrics_no_cost = _run(strategy, df, fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    _, metrics_with_cost = _run(
        strategy, df, fee_rate=0.00015, tax_rate=0.0018, slippage=0.001
    )

    # 거래가 있으면 비용이 줄어들어야 함
    if metrics_no_cost["trade_count"] > 0:
        assert metrics_with_cost["final_equity"] < metrics_no_cost["final_equity"], (
            "비용 적용 시 final_equity가 더 낮아야 한다"
        )
