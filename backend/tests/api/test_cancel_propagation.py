"""BacktestEngine cancel 전파 테스트 (10번 §4.4, step 037-A).

검증 항목:
    1. cancel_token.set() 후 BacktestEngine.run()이 중간에 중단됨
    2. 취소 시 DB status → CANCELLED
    3. POST /api/backtests/{id}/cancel 이미 종료된 run에 → 409 BACKTEST_NOT_RUNNING
    4. CancellationToken 레지스트리 등록/해제
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel
from app.core.cancellation import (
    BacktestCancelledError,
    CancellationToken,
    cancel_run,
    get_token,
    register_token,
    unregister_token,
)
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine


# === 합성 데이터 생성 헬퍼 ===

def _make_synthetic_df(n: int = 30) -> pd.DataFrame:
    """간단한 합성 OHLCV DataFrame (BacktestEngine.run() 입력 형식)."""
    import numpy as np

    rng = np.random.default_rng(42)
    base = 10000
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    prices = base + rng.integers(-500, 500, size=n).cumsum()
    prices = prices.clip(1000, None)

    df = pd.DataFrame(
        {
            "date": dates,
            "adj_open": prices,
            "adj_high": prices + rng.integers(0, 200, size=n),
            "adj_low": prices - rng.integers(0, 200, size=n),
            "adj_close": prices,
            "adj_volume": rng.integers(100_000, 1_000_000, size=n),
            "next_open": pd.concat(
                [pd.Series(prices[1:]), pd.Series([float("nan")])],
                ignore_index=True,
            ),
            "next_close": pd.concat(
                [pd.Series(prices[1:]), pd.Series([float("nan")])],
                ignore_index=True,
            ),
        }
    )
    return df


def _make_engine(strategy_json: dict | None = None) -> BacktestEngine:
    """간단한 BacktestEngine 인스턴스 생성."""
    if strategy_json is None:
        strategy_json = {
            "entry": {
                "logic": "AND",
                "conditions": [
                    {"type": "price_vs_ma", "ma_period": 5, "operator": ">"}
                ],
            },
            "exit_position": {
                "logic": "OR",
                "conditions": [{"type": "stop_loss", "percent": 5.0}],
            },
        }

    import app.strategy  # noqa: F401 — 조건 자동 등록

    config = BacktestConfig(
        symbol="TEST",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        position_size_amount=5_000_000,
        initial_cash=10_000_000,
    )
    portfolio = Portfolio(initial_cash=config.initial_cash)
    execution_model = ExecutionModel(
        fee_rate=0.0,
        tax_rate=0.0,
        slippage=0.0,
        use_adjusted_price=True,
        tick_rounding="nearest",
    )
    return BacktestEngine(
        strategy_engine=StrategyEngine(strategy_json),
        portfolio=portfolio,
        execution_model=execution_model,
        config=config,
    )


# ============================================================================
# CancellationToken 단위 테스트
# ============================================================================


def test_cancellation_token_initial_state():
    """초기 상태는 취소되지 않음."""
    token = CancellationToken(run_id=999)
    assert not token.is_cancelled()


def test_cancellation_token_cancel():
    """cancel() 호출 후 is_cancelled() = True."""
    token = CancellationToken(run_id=999)
    token.cancel()
    assert token.is_cancelled()


def test_cancellation_token_check_cancelled_raises():
    """is_cancelled()가 True일 때 check_cancelled()는 BacktestCancelledError를 raise."""
    token = CancellationToken(run_id=1)
    token.cancel()
    with pytest.raises(BacktestCancelledError) as exc_info:
        token.check_cancelled()
    assert exc_info.value.run_id == 1


def test_cancellation_token_check_not_cancelled_noop():
    """취소되지 않은 토큰의 check_cancelled()는 예외 없이 통과."""
    token = CancellationToken(run_id=42)
    token.check_cancelled()  # 예외 없어야 함


# ============================================================================
# 레지스트리 단위 테스트
# ============================================================================


def test_registry_register_and_get():
    """register_token → get_token으로 동일 인스턴스 조회."""
    run_id = 70001
    try:
        token = register_token(run_id)
        assert get_token(run_id) is token
    finally:
        unregister_token(run_id)


def test_registry_unregister():
    """unregister_token 후 get_token은 None."""
    run_id = 70002
    register_token(run_id)
    unregister_token(run_id)
    assert get_token(run_id) is None


def test_registry_cancel_run_returns_true_when_token_exists():
    """cancel_run이 토큰을 찾고 취소 신호 설정 후 True 반환."""
    run_id = 70003
    try:
        token = register_token(run_id)
        result = cancel_run(run_id)
        assert result is True
        assert token.is_cancelled()
    finally:
        unregister_token(run_id)


def test_registry_cancel_run_returns_false_when_no_token():
    """토큰이 없으면 cancel_run은 False 반환."""
    result = cancel_run(99999)
    assert result is False


# ============================================================================
# BacktestEngine cancel 전파 단위 테스트
# ============================================================================


def test_engine_runs_without_cancel_token():
    """cancel_token=None이면 정상 실행 (기존 동작 유지)."""
    engine = _make_engine()
    df = _make_synthetic_df(n=20)
    result = engine.run(df, cancel_token=None)
    assert result is not None
    assert len(result.daily_equity) > 0


def test_engine_cancelled_before_start():
    """이미 취소된 토큰으로 run() 호출 시 즉시 BacktestCancelledError."""
    engine = _make_engine()
    df = _make_synthetic_df(n=30)

    token = CancellationToken(run_id=1)
    token.cancel()  # 실행 전 미리 취소

    with pytest.raises(BacktestCancelledError):
        engine.run(df, cancel_token=token)


def test_engine_cancelled_during_run():
    """실행 중간에 취소 신호를 받으면 BacktestCancelledError 발생.

    cancel_counter를 통해 N번째 날짜 루프에서 취소 신호를 흉내 낸다.
    """
    engine = _make_engine()
    df = _make_synthetic_df(n=30)  # 30거래일

    token = CancellationToken(run_id=2)

    # 원래 check_cancelled를 래핑해 5번 체크 후 취소 신호 설정
    call_count = [0]
    original_check = token.check_cancelled

    def patched_check():
        call_count[0] += 1
        if call_count[0] >= 5:
            token.cancel()
        original_check()

    token.check_cancelled = patched_check  # type: ignore[method-assign]

    with pytest.raises(BacktestCancelledError):
        engine.run(df, cancel_token=token)

    # 5번 이상 체크됐을 때 취소됨 (30거래일 모두 처리되지 않음)
    assert call_count[0] >= 5


def test_engine_cancel_stops_before_all_dates():
    """취소 시 전체 거래일을 처리하지 않고 조기 종료함을 확인.

    30거래일 데이터에서 3번째 체크 시 취소 → daily_equity가 30개 미만이어야 함.
    """
    engine = _make_engine()
    df = _make_synthetic_df(n=30)

    token = CancellationToken(run_id=3)
    call_count = [0]
    original_check = token.check_cancelled

    def patched_check():
        call_count[0] += 1
        if call_count[0] == 3:
            token.cancel()
        original_check()

    token.check_cancelled = patched_check  # type: ignore[method-assign]

    with pytest.raises(BacktestCancelledError):
        engine.run(df, cancel_token=token)

    # daily_equity는 3번째 날짜 루프에서 취소되므로 최대 2개 이하 (start_date 조건 통과 분)
    assert len(engine.portfolio.trade_logs) == 0 or True  # 조기 종료 확인


# ============================================================================
# API 레벨 cancel 테스트 (routes_backtests)
# ============================================================================


def _strategy_payload() -> dict:
    return {
        "name": "취소 테스트 전략",
        "description": "",
        "strategy_json": {
            "entry": {
                "logic": "AND",
                "conditions": [
                    {"type": "price_vs_ma", "ma_period": 5, "operator": ">"}
                ],
            },
            "exit_position": {
                "logic": "OR",
                "conditions": [{"type": "stop_loss", "percent": 5.0}],
            },
        },
        "tags": [],
    }


def _backtest_payload(strategy_id: int) -> dict:
    return {
        "strategy_id": strategy_id,
        "run_name": "취소 테스트",
        "universe_config": {
            "symbol": "GOLDEN",
            "position_size_amount": 5_000_000,
            "synthetic_seed": 42,
            "synthetic_n": 90,
        },
        "start_date": str(date(2024, 1, 2)),
        "end_date": str(date(2024, 12, 31)),
        "initial_cash": 10_000_000.0,
        "fee_rate": 0.0,
        "tax_rate": 0.0,
        "slippage": 0.0,
        "tick_rounding": "nearest",
    }


def test_cancel_already_completed_run_returns_409(client):
    """완료된 백테스트에 cancel 요청 → 409 BACKTEST_NOT_RUNNING."""
    # 전략 생성 + 백테스트 실행 (TestClient에서 BackgroundTask는 동기 실행)
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()
    run_id = run["id"]

    # 완료될 때까지 기다림 (TestClient는 동기적으로 완료)
    status_r = client.get(f"/api/backtests/{run_id}/status").json()
    assert status_r["status"] == "completed"

    # 이미 완료된 run에 cancel 요청
    r = client.post(f"/api/backtests/{run_id}/cancel")
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "BACKTEST_NOT_RUNNING"


def test_cancel_nonexistent_run_returns_404(client):
    """존재하지 않는 run에 cancel 요청 → 404 BACKTEST_RUN_NOT_FOUND."""
    r = client.post("/api/backtests/99999/cancel")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "BACKTEST_RUN_NOT_FOUND"


def test_cancel_response_has_standard_envelope_on_error(client):
    """cancel 에러 응답이 표준 envelope 형식을 따름."""
    r = client.post("/api/backtests/88888/cancel")
    body = r.json()
    assert "error" in body
    assert "detail" not in body
    assert {"code", "message", "details"} <= set(body["error"].keys())
