"""CSV/ZIP Export API 테스트."""

import io
import zipfile
from datetime import date


def _strategy_payload():
    return {
        "name": "테스트",
        "description": "",
        "strategy_json": {
            "entry": {"logic": "AND", "conditions": [
                {"type": "price_vs_ma", "ma_period": 5, "operator": ">"}
            ]},
            "exit_position": {"logic": "OR", "conditions": [
                {"type": "take_profit", "percent": 5.0, "trigger": "intraday_high"},
                {"type": "stop_loss", "percent": 3.0},
            ]},
        },
        "tags": [],
    }


def _backtest_payload(strategy_id):
    return {
        "strategy_id": strategy_id,
        "run_name": "GOLDEN",
        "universe_config": {
            "symbol": "GOLDEN", "position_size_amount": 5_000_000,
            "synthetic_seed": 42, "synthetic_n": 90,
        },
        "start_date": str(date(2024, 1, 2)),
        "end_date": str(date(2024, 12, 31)),
        "initial_cash": 10_000_000.0,
        "fee_rate": 0.0, "tax_rate": 0.0, "slippage": 0.0, "tick_rounding": "nearest",
    }


def _setup(client):
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()
    return run["id"]


def test_export_summary_csv(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/summary")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    text = r.content.decode("utf-8-sig")
    assert "trade_count" in text  # header
    assert "8" in text  # frozen Phase 1 골든 결과


def test_export_trades_csv(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/trades")
    text = r.content.decode("utf-8-sig")
    # header
    assert "symbol" in text
    # 거래 9건 + 헤더 1줄
    line_count = sum(1 for line in text.splitlines() if line.strip())
    assert line_count == 9 + 1


def test_export_daily_equity_csv(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/daily-equity")
    text = r.content.decode("utf-8-sig")
    assert "drawdown_pct" in text
    line_count = sum(1 for line in text.splitlines() if line.strip())
    assert line_count == 90 + 1


def test_export_cash_events_csv(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/cash-events")
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    assert "event_type" in text


def test_export_strategy_snapshot_json(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/strategy")
    assert r.status_code == 200
    body = r.json()
    assert body["entry"]["conditions"][0]["type"] == "price_vs_ma"


def test_export_zip(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    assert {
        "summary.csv", "trades.csv", "daily_equity.csv",
        "cash_events.csv", "strategy_snapshot.json",
    } == names


def test_export_invalid_kind(client):
    run_id = _setup(client)
    r = client.get(f"/api/backtests/{run_id}/export/unknown")
    assert r.status_code == 400


def test_export_unknown_run(client):
    r = client.get("/api/backtests/9999/export/zip")
    assert r.status_code == 404
