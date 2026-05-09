"""Backtest API 테스트.

dev 모드 합성 데이터 (synthetic_seed)로 end-to-end 검증.
TestClient의 BackgroundTask는 응답 후 동기 실행.
"""

from datetime import date


def _strategy_payload() -> dict:
    return {
        "name": "테스트 전략",
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
                "conditions": [
                    {"type": "take_profit", "percent": 5.0, "trigger": "intraday_high"},
                    {"type": "stop_loss", "percent": 3.0},
                ],
            },
        },
        "tags": [],
    }


def _backtest_payload(strategy_id: int) -> dict:
    return {
        "strategy_id": strategy_id,
        "run_name": "synthetic seed=42",
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


def test_create_runs_synchronously_in_test_client(client):
    """TestClient의 BackgroundTask는 응답 후 동기 실행 → 곧바로 completed."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    r = client.post("/api/backtests", json=_backtest_payload(s["id"]))
    assert r.status_code == 202
    run = r.json()
    assert run["status"] in ("pending", "running", "completed")

    # status 조회
    status = client.get(f"/api/backtests/{run['id']}/status").json()
    assert status["status"] == "completed"
    assert status["progress_pct"] == 100.0


def test_summary_after_completion(client):
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()

    summary = client.get(f"/api/backtests/{run['id']}/summary").json()
    assert summary["status"] == "completed"
    assert summary["summary"] is not None
    # Phase 1 골든 frozen값과 일치 (8 trades, 37.5% win rate)
    assert summary["summary"]["trade_count"] == 8
    assert summary["summary"]["final_equity"] == 10_188_570.0


def test_trades_list(client):
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()

    body = client.get(f"/api/backtests/{run['id']}/trades").json()
    # BUY 9건 + SELL 8건 = 9 trade_groups (1개 미청산)
    assert body["total_count"] == 9
    first = body["items"][0]
    assert "executions" in first
    assert len(first["executions"]) >= 1


def test_daily_equity_list(client):
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()

    body = client.get(f"/api/backtests/{run['id']}/daily-equity").json()
    assert body["total_count"] == 90


def test_chart_data(client):
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()

    body = client.get(f"/api/backtests/{run['id']}/chart-data").json()
    assert len(body["candles"]) == 90
    assert all({"time", "open", "high", "low", "close"} <= set(c.keys()) for c in body["candles"][:3])
    assert len(body["markers"]) == 17  # 9 BUY + 8 SELL
    assert len(body["equity_curve"]) == 90


def test_chart_data_404(client):
    assert client.get("/api/backtests/9999/chart-data").status_code == 404


def test_status_404_for_unknown(client):
    r = client.get("/api/backtests/9999/status")
    assert r.status_code == 404


def test_summary_404_for_unknown(client):
    r = client.get("/api/backtests/9999/summary")
    assert r.status_code == 404
