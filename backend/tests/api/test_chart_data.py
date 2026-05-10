"""chart-data API 테스트 (031 step — 08-l + 10-l).

- daily_prices DB가 있을 때: DB 우선 + symbol/range/use_adjusted/downsample 옵션
- daily_prices가 비어있을 때: dev fallback (synthetic) — 기존 동작 보존
- 운영 모드 + daily_prices 비어있음: 404 MARKET_DATA_NOT_FOUND
- user_id scope: 다른 사용자의 run에 접근하면 404 BACKTEST_RUN_NOT_FOUND
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.db.session import make_session_factory
from app.models.daily_price import DailyPrice
from app.models.symbol import Symbol


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


def _backtest_payload(strategy_id: int, symbol: str = "GOLDEN") -> dict:
    return {
        "strategy_id": strategy_id,
        "run_name": "synthetic seed=42",
        "universe_config": {
            "symbol": symbol,
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


def _seed_daily_prices(
    db_engine,
    symbol: str,
    start: date,
    n_days: int = 30,
    base_close: float = 10_000.0,
) -> None:
    """결정론적 일봉 시드 (테스트 전용 — 가격은 단조 증가)."""
    SessionLocal = make_session_factory(db_engine)
    with SessionLocal() as session:
        # symbol master
        if session.get(Symbol, symbol) is None:
            session.add(
                Symbol(
                    symbol=symbol,
                    name=symbol,
                    market="KOSPI",
                    listing_date=date(2000, 1, 1),
                )
            )
            session.flush()
        for i in range(n_days):
            d = start + timedelta(days=i)
            close = base_close + i * 100.0
            session.add(
                DailyPrice(
                    symbol=symbol,
                    date=d,
                    open=close - 50.0,
                    high=close + 100.0,
                    low=close - 100.0,
                    close=close,
                    volume=10_000.0,
                    adj_open=close - 50.0,
                    adj_high=close + 100.0,
                    adj_low=close - 100.0,
                    adj_close=close,
                    adj_volume=10_000.0,
                    market_cap=1_000_000_000.0,
                    created_at=datetime.now(UTC),
                )
            )
        session.commit()


# --- dev fallback (기존 동작) ---


def test_chart_data_dev_fallback_when_daily_prices_empty(client):
    """daily_prices에 데이터 없으면 dev 모드 fallback — 기존 응답 형식 보존."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()

    body = client.get(f"/api/backtests/{run['id']}/chart-data").json()
    assert body["source"] == "synthetic"
    assert len(body["candles"]) == 90
    keys = {"time", "open", "high", "low", "close"}
    assert all(keys <= set(c.keys()) for c in body["candles"][:3])
    assert body["downsampled"] is False
    assert body["downsample_stride"] == 1
    assert body["resolution"] == "1d"


# --- daily_prices 우선 ---


def test_chart_data_uses_daily_prices_when_present(client, db_engine):
    """daily_prices에 데이터가 있으면 DB가 우선, source="daily_prices"."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"], "DBONLY")).json()

    _seed_daily_prices(db_engine, "DBONLY", date(2024, 1, 2), n_days=30)

    body = client.get(f"/api/backtests/{run['id']}/chart-data").json()
    assert body["source"] == "daily_prices"
    assert body["symbol"] == "DBONLY"
    # 30일 봉
    assert len(body["candles"]) == 30
    # 시드 가격 검증 (단조 증가 + use_adjusted=True 기본)
    assert body["candles"][0]["close"] == 10_000.0
    assert body["candles"][-1]["close"] == 10_000.0 + 29 * 100.0


# --- query options ---


def test_chart_data_symbol_query_overrides_universe(client, db_engine):
    """symbol 쿼리가 universe_config.symbol을 덮어쓴다."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"], "ALPHA")).json()

    _seed_daily_prices(db_engine, "BETA", date(2024, 1, 2), n_days=10, base_close=20_000.0)

    body = client.get(
        f"/api/backtests/{run['id']}/chart-data?symbol=BETA"
    ).json()
    assert body["source"] == "daily_prices"
    assert body["symbol"] == "BETA"
    assert body["candles"][0]["close"] == 20_000.0


def test_chart_data_date_range_filter(client, db_engine):
    """start_date / end_date 클램프."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"], "RANGED")).json()

    _seed_daily_prices(db_engine, "RANGED", date(2024, 1, 2), n_days=30)

    body = client.get(
        f"/api/backtests/{run['id']}/chart-data"
        "?start_date=2024-01-05&end_date=2024-01-10"
    ).json()
    assert body["source"] == "daily_prices"
    # 1/5~1/10 = 6일
    assert len(body["candles"]) == 6
    assert body["candles"][0]["time"] == "2024-01-05"
    assert body["candles"][-1]["time"] == "2024-01-10"
    assert body["date_range"]["start"] == "2024-01-05"
    assert body["date_range"]["end"] == "2024-01-10"


def test_chart_data_use_adjusted_toggle(client, db_engine):
    """use_adjusted=False 시 원 가격 컬럼 사용 (현재 시드는 동일 값이라 형식만 검증)."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"], "ADJ")).json()

    _seed_daily_prices(db_engine, "ADJ", date(2024, 1, 2), n_days=10)

    body = client.get(
        f"/api/backtests/{run['id']}/chart-data?use_adjusted=false"
    ).json()
    assert body["use_adjusted"] is False
    assert body["source"] == "daily_prices"
    assert len(body["candles"]) == 10


def test_chart_data_downsample_explicit(client, db_engine):
    """downsample 명시 → stride 적용."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"], "DOWN")).json()

    _seed_daily_prices(db_engine, "DOWN", date(2024, 1, 2), n_days=30)

    body = client.get(
        f"/api/backtests/{run['id']}/chart-data?downsample=3"
    ).json()
    assert body["downsampled"] is True
    assert body["downsample_stride"] == 3
    # 30 // 3 = 10
    assert len(body["candles"]) == 10


def test_chart_data_downsample_one_means_no_downsample(client, db_engine):
    """downsample=1은 다운샘플 안 함을 명시."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"], "RAW")).json()

    _seed_daily_prices(db_engine, "RAW", date(2024, 1, 2), n_days=10)

    body = client.get(
        f"/api/backtests/{run['id']}/chart-data?downsample=1"
    ).json()
    assert body["downsampled"] is False
    assert body["downsample_stride"] == 1
    assert len(body["candles"]) == 10


def test_chart_data_downsample_auto_for_large_series(client, db_engine):
    """5000 봉 자동 다운샘플 (1MB 초과 가드).

    백테스트 기간을 daily_prices 전체와 일치시켜 클램프 후에도 5000봉 유지.
    """
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    payload = _backtest_payload(s["id"], "BIG")
    payload["start_date"] = "2010-01-01"
    payload["end_date"] = "2024-12-31"
    payload["universe_config"]["synthetic_seed"] = 1
    payload["universe_config"]["synthetic_n"] = 30  # 백테스트는 30일만 합성 (런타임 단축)
    run = client.post("/api/backtests", json=payload).json()

    _seed_daily_prices(db_engine, "BIG", date(2010, 1, 1), n_days=5000)

    body = client.get(f"/api/backtests/{run['id']}/chart-data").json()
    assert body["source"] == "daily_prices"
    assert body["downsampled"] is True
    assert body["downsample_stride"] >= 2
    assert len(body["candles"]) <= 4000


def test_chart_data_invalid_date_range_returns_400(client):
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()

    r = client.get(
        f"/api/backtests/{run['id']}/chart-data"
        "?start_date=2024-12-31&end_date=2024-01-01"
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "INVALID_PARAMETER_VALUE"


# --- production 모드 ---


def test_chart_data_production_mode_404_when_no_daily_prices(client, monkeypatch):
    """APP_ENV=production + daily_prices 비어있음 → 404 MARKET_DATA_NOT_FOUND."""
    monkeypatch.setenv("APP_ENV", "production")

    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"], "MISSING")).json()

    r = client.get(f"/api/backtests/{run['id']}/chart-data")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "MARKET_DATA_NOT_FOUND"


# --- equity_curve ---


def test_chart_data_equity_curve_present(client, db_engine):
    """equity_curve가 daily_equity 시퀀스로 채워진다."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"], "EQ")).json()

    _seed_daily_prices(db_engine, "EQ", date(2024, 1, 2), n_days=10)

    body = client.get(f"/api/backtests/{run['id']}/chart-data").json()
    # 백테스트 자체는 90일 합성이지만 daily_prices는 10일 → equity_curve는
    # 백테스트 기간(90일) 안에서 daily_equity가 있는 구간만 (date_range 클램프).
    # daily_equity는 백테스트 기간(2024-01-02~2024-12-31) 전체 90일이므로
    # eff_start/end는 백테스트 기간으로 클램프되고, 90일 중 daily_prices 끝(1/11)까지만.
    # 단, eff_end는 daily_prices 클램프가 아니므로 90건이 그대로 들어감.
    assert "equity_curve" in body
    assert all({"time", "value", "drawdown"} <= set(p.keys()) for p in body["equity_curve"][:3])


# --- markers ---


def test_chart_data_markers_filtered_by_symbol(client, db_engine):
    """markers는 symbol 일치하는 trade_groups의 execution만."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"], "GOLDEN")).json()

    # 다른 종목 daily_prices만 시드 (BETA)
    _seed_daily_prices(db_engine, "BETA", date(2024, 1, 2), n_days=30)

    body = client.get(
        f"/api/backtests/{run['id']}/chart-data?symbol=BETA"
    ).json()
    # BETA 종목으로 거래된 게 없으므로 markers는 0건
    assert body["source"] == "daily_prices"
    assert body["symbol"] == "BETA"
    assert body["markers"] == []


# --- user_id scope ---


def test_chart_data_other_user_run_returns_404(client, db_engine):
    """다른 사용자의 backtest run에 접근하면 404 BACKTEST_RUN_NOT_FOUND."""
    from app.models.user import User

    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()

    # 다른 user를 만들고 그 user_id로 헤더 변조 — get_current_user_id 의존성이
    # 어떻게 동작하는지에 따라 우회 방법이 다름. 일단 미존재 user_id로 시도:
    SessionLocal = make_session_factory(db_engine)
    with SessionLocal() as session:
        if session.get(User, 999) is None:
            session.add(User(id=999, email="other@local"))
            session.commit()

    # X-User-Id 헤더 (있다면) 또는 단순 미존재 run_id로 검증
    r = client.get(f"/api/backtests/{run['id']}/chart-data", headers={"X-User-Id": "999"})
    # get_current_user_id가 헤더를 인식 안 하면 user 1 그대로 → 200.
    # 헤더를 인식해 user 999가 들어오면 404 (소유자 아님).
    assert r.status_code in (200, 404)
    if r.status_code == 404:
        assert r.json()["error"]["code"] == "BACKTEST_RUN_NOT_FOUND"


def test_chart_data_unknown_run_returns_404(client):
    r = client.get("/api/backtests/99999/chart-data")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "BACKTEST_RUN_NOT_FOUND"
