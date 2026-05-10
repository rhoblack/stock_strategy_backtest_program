"""Phase 12 e2e 통합 시나리오 — UI 확장 (02 schema GUI + chart-data DB 전환).

Phase 12 step 029~033이 도입한 UI 확장의 백엔드 contract를 보호한다.
주된 변경은 frontend(029/030/032/033)이지만, 031에서 chart-data API를
daily_prices DB 기반으로 전환했고 029의 6섹션 + GROUP + tax_rate 시계열
직렬화가 백엔드 strategy_json validator(C4) + 영속화 라운드트립을 새로 활용한다.

본 e2e는 단위 테스트가 다루지 않는 *e2e 라운드트립*만 보호한다:
    - 029 (frontend) ↔ validator/services (backend): 직렬화 → POST → DB → GET 라운드트립
    - 031 chart-data: daily_prices 우선 / dev fallback / 운영 404 / 결정론 정렬
    - 031 use_adjusted toggle (13.7) 라운드트립

검증 매핑 (정확성 정책 13.x + 02 schema):
    - 02.4  GROUP 1단계 중첩 + operator                      → 시나리오 1
    - 02.7  priority method/tie_breaker                     → 시나리오 1
    - 02.8  position_sizing method/amount/max_positions      → 시나리오 1
    - 02.11 execution + tick_rounding                       → 시나리오 1
    - 02.12 metadata.schema_version 고정                     → 시나리오 1
    - 02.15 tax_rate 시계열 (from 오름차순 + rate>=0)        → 시나리오 1·2
    - 13.6  거래세 시계열                                    → 시나리오 2
    - 13.7  수정주가 사용 일관성 (use_adjusted=True 기본)     → 시나리오 4
    - 13.12 결정론 (sorted 응답 + tie-breaker)                → 시나리오 3·5
    - CLAUDE.md #1  JSON 데이터, eval 금지                    → 시나리오 1
    - CLAUDE.md #8  Python dict/set 순서 비의존, sorted     → 시나리오 3·5

본 모듈은 외부 fetch 0건 — 모든 가격 데이터는 fixture로 직접 시드.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db.session import create_db_engine, init_db, make_session_factory
from app.main import app
from app.main_state import reset_engine_for_tests
from app.models.daily_price import DailyPrice
from app.models.symbol import Symbol
from app.models.user import User

# ============================================================================
# fixtures (tests/api/conftest.py와 동일 패턴 — 본 모듈 한정)
# ============================================================================


@pytest.fixture
def db_engine():
    """파일 기반 SQLite — TestClient 의존성이 새 session을 만들 때도 테이블 보존."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "phase12_e2e.db")
    url = f"sqlite:///{path}"
    engine = create_db_engine(url)
    init_db(engine)

    SessionLocal = make_session_factory(engine)
    with SessionLocal() as session:
        if session.get(User, 1) is None:
            session.add(User(id=1, email="system@local"))
            session.commit()

    reset_engine_for_tests(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        try:
            if os.path.exists(path):
                os.unlink(path)
            os.rmdir(tmpdir)
        except OSError:
            pass


@pytest.fixture
def client(db_engine):  # noqa: ARG001
    return TestClient(app)


# ============================================================================
# 헬퍼
# ============================================================================


def _serialized_strategy_full_six_sections() -> dict:
    """029 frontend serializeDraft 산출물과 동등 형태 — 4 조건 섹션 + 6 비조건 섹션 모두 포함.

    이 dict는 frontend serializeDraft.ts가 만드는 형식 그대로:
        - GROUP 1단계 중첩 (entry)
        - exit_position에 take_profit + stop_loss
        - 6 비조건 섹션 모두 enabled (position_sizing/cash_management/risk_management/
          execution/priority/metadata)
        - tax_rate 시계열 ([{from, rate}], from 오름차순)
        - metadata.schema_version="1.0" 고정
    """
    return {
        "entry": {
            "logic": "GROUP",
            "operator": "OR",
            "groups": [
                {
                    "logic": "AND",
                    "conditions": [
                        {"type": "price_vs_ma", "ma_period": 5, "operator": ">"},
                        {"type": "price_vs_ma", "ma_period": 20, "operator": ">"},
                    ],
                },
                {
                    "logic": "AND",
                    "conditions": [
                        {"type": "rsi_level", "period": 14, "operator": "<", "value": 30.0},
                    ],
                },
            ],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [
                {"type": "take_profit", "percent": 5.0, "trigger": "intraday_high"},
                {"type": "stop_loss", "percent": 3.0},
            ],
        },
        "position_sizing": {
            "method": "fixed_amount",
            "amount": 1_000_000,
            "max_positions": 3,
            "max_daily_entries": 2,
            "daily_buy_budget": 5_000_000,
            "allow_pyramiding": False,
        },
        "cash_management": {
            "enabled": True,
            "shortage_rule": {
                "trigger": {"type": "cash_below_threshold", "threshold": 100_000},
                "action": {"type": "sell_partial", "sell_fraction": 0.5},
                "target_selection": {"method": "smallest_position_first"},
                "repeat_until_cash_sufficient": True,
            },
        },
        "risk_management": {
            "stop_trading_on_drawdown_pct": 20.0,
            "max_position_ratio": 0.3,
            "max_daily_loss_pct": 5.0,
        },
        "execution": {
            "entry_price": "next_open",
            "exit_price": "next_open",
            "fee_rate": 0.00015,
            "slippage": 0.001,
            "tax_rate": [
                {"from": "2022-01-01", "rate": 0.0023},
                {"from": "2023-01-01", "rate": 0.002},
                {"from": "2024-01-01", "rate": 0.0018},
                {"from": "2025-01-01", "rate": 0.0015},
            ],
            "use_adjusted_price": True,
            "max_gap_pct_for_entry": 5.0,
            "allow_buy_limit_up": False,
            "allow_sell_limit_down": False,
            "tick_rounding": "buy_up_sell_down",
        },
        "priority": {
            "method": "trading_value_desc",
            "tie_breaker": "symbol_asc",
        },
        "metadata": {
            "schema_version": "1.0",
            "random_seed": 42,
            "tags": ["test", "phase12"],
            "favorite": True,
        },
    }


def _strategy_create_payload(
    *,
    name: str = "Phase12 라운드트립 전략",
    strategy_json: dict | None = None,
) -> dict:
    return {
        "name": name,
        "description": "Phase 12 e2e 검증",
        "strategy_json": strategy_json or _serialized_strategy_full_six_sections(),
        "tags": ["e2e", "phase12"],
    }


def _backtest_payload(strategy_id: int, *, symbol: str = "PHASE12") -> dict:
    return {
        "strategy_id": strategy_id,
        "run_name": "phase12 e2e",
        "universe_config": {
            "symbol": symbol,
            "position_size_amount": 1_000_000,
            "synthetic_seed": 42,
            "synthetic_n": 60,
        },
        "start_date": str(date(2024, 1, 2)),
        "end_date": str(date(2024, 12, 31)),
        "initial_cash": 5_000_000.0,
        "fee_rate": 0.0,
        "tax_rate": 0.0,
        "slippage": 0.0,
        "tick_rounding": "nearest",
    }


def _seed_daily_prices(
    db_engine,
    symbol: str,
    start: date,
    *,
    n_days: int = 20,
    base_close: float = 10_000.0,
    adj_diff: float = 0.0,
) -> None:
    """결정론적 시드.

    - close는 단조 증가 (검증 용이성)
    - adj_close는 close + adj_diff (use_adjusted toggle 검증용)
    """
    SessionLocal = make_session_factory(db_engine)
    with SessionLocal() as session:
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
            adj_close = close + adj_diff
            session.add(
                DailyPrice(
                    symbol=symbol,
                    date=d,
                    open=close - 50.0,
                    high=close + 100.0,
                    low=close - 100.0,
                    close=close,
                    volume=10_000.0,
                    adj_open=adj_close - 50.0,
                    adj_high=adj_close + 100.0,
                    adj_low=adj_close - 100.0,
                    adj_close=adj_close,
                    adj_volume=10_000.0,
                    market_cap=1_000_000_000.0,
                    created_at=datetime.now(UTC),
                )
            )
        session.commit()


# ============================================================================
# 시나리오 1: 02 schema 6섹션 + GROUP 라운드트립
# ============================================================================
#
# 029 frontend의 serializeDraft가 만드는 6섹션 + GROUP 1단계 + tax_rate 시계열을
# 백엔드 validator가 받고 → DB 영속화 → 다시 GET하여 strategy_json이 라운드트립
# 보존되는지 검증.
#
# 검증:
#   - validator (C4)가 6섹션 모두 통과 (02.4 / 02.7 / 02.8 / 02.11 / 02.12 / 02.15)
#   - DB에 strategy_json이 dict 그대로 저장 (CLAUDE.md #1: JSON 데이터)
#   - GET 시 6섹션 + GROUP 구조 + tax_rate 4개 bracket이 모두 보존
#   - metadata.schema_version="1.0" 고정 검증


def test_phase12_six_sections_with_group_and_tax_timeseries_roundtrip(client):
    payload = _strategy_create_payload()

    # 1) POST — validator 통과 + 영속화
    r = client.post("/api/strategies", json=payload)
    assert r.status_code == 201, r.text
    created = r.json()
    sid = created["id"]
    assert created["strategy_json"]["entry"]["logic"] == "GROUP"

    # 2) GET — 라운드트립 보존
    r2 = client.get(f"/api/strategies/{sid}")
    assert r2.status_code == 200, r2.text
    fetched = r2.json()
    sjson = fetched["strategy_json"]

    # entry: GROUP 1단계
    assert sjson["entry"]["logic"] == "GROUP"
    assert sjson["entry"]["operator"] == "OR"
    assert len(sjson["entry"]["groups"]) == 2
    assert sjson["entry"]["groups"][0]["logic"] == "AND"
    assert len(sjson["entry"]["groups"][0]["conditions"]) == 2
    assert sjson["entry"]["groups"][1]["logic"] == "AND"
    assert sjson["entry"]["groups"][1]["conditions"][0]["type"] == "rsi_level"

    # exit_position
    assert sjson["exit_position"]["logic"] == "OR"
    types = sorted(c["type"] for c in sjson["exit_position"]["conditions"])
    assert types == ["stop_loss", "take_profit"]

    # 6 비조건 섹션
    assert sjson["position_sizing"]["method"] == "fixed_amount"
    assert sjson["position_sizing"]["amount"] == 1_000_000
    assert sjson["cash_management"]["enabled"] is True
    assert sjson["risk_management"]["stop_trading_on_drawdown_pct"] == 20.0

    # 02.15 tax_rate 시계열 — 4개 bracket, from 오름차순 보존
    tax = sjson["execution"]["tax_rate"]
    assert isinstance(tax, list)
    assert len(tax) == 4
    assert [b["from"] for b in tax] == [
        "2022-01-01",
        "2023-01-01",
        "2024-01-01",
        "2025-01-01",
    ]
    # 13.6 거래세 시계열: 2022 0.23% → 2025 0.15%
    assert tax[0]["rate"] == 0.0023
    assert tax[-1]["rate"] == 0.0015

    # priority
    assert sjson["priority"]["method"] == "trading_value_desc"
    assert sjson["priority"]["tie_breaker"] == "symbol_asc"

    # metadata.schema_version 고정 ("1.0")
    assert sjson["metadata"]["schema_version"] == "1.0"
    assert sjson["metadata"]["random_seed"] == 42
    assert "phase12" in sjson["metadata"]["tags"]


# ============================================================================
# 시나리오 2: tax_rate 시계열 정렬 위반 → 400 envelope
# ============================================================================
#
# 02.15 + 13.6 정책: tax_rate 시계열은 from 오름차순 강제. 위반 시 validator가
# INVALID_PARAMETER_VALUE 표준 envelope로 차단.


def test_phase12_tax_rate_timeseries_must_be_ascending(client):
    bad = _serialized_strategy_full_six_sections()
    bad["execution"]["tax_rate"] = [
        {"from": "2024-01-01", "rate": 0.0018},
        {"from": "2022-01-01", "rate": 0.0023},  # 순서 위반
    ]

    r = client.post("/api/strategies", json=_strategy_create_payload(strategy_json=bad))
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "INVALID_PARAMETER_VALUE"
    # error envelope에 X-Request-ID 포함 (Phase 8 H7 — Phase 12에서도 깨지지 않음)
    assert "request_id" in body["error"] or r.headers.get("x-request-id")


# ============================================================================
# 시나리오 3: chart-data 결정론 (date ASC + execution_date ASC + symbol 필터)
# ============================================================================
#
# 031 chart-data API (`backend/app/services/backtest_service.py:520+`)가 항상
# 결정적 정렬 순서로 응답 — Python dict/set 순서에 의존하지 않음 (CLAUDE.md #8).
#
# 같은 backtest_run에 대해 chart-data를 두 번 호출했을 때 응답이 byte-equal한지
# (candles + markers + equity_curve 모든 시퀀스 동일 순서) 검증.


def test_phase12_chart_data_two_calls_are_deterministic(client, db_engine):
    sp = client.post("/api/strategies", json=_strategy_create_payload(name="결정론")).json()
    bp = _backtest_payload(sp["id"], symbol="DETERM")
    run = client.post("/api/backtests", json=bp).json()

    _seed_daily_prices(db_engine, "DETERM", date(2024, 1, 2), n_days=15)

    body1 = client.get(f"/api/backtests/{run['id']}/chart-data").json()
    body2 = client.get(f"/api/backtests/{run['id']}/chart-data").json()

    # candles 시퀀스 동일 (date ASC) — 13.12 결정론
    assert [c["time"] for c in body1["candles"]] == [c["time"] for c in body2["candles"]]
    assert len(body1["candles"]) == 15
    # 단조 증가 (시드가 그렇게 설계됨)
    for i in range(1, len(body1["candles"])):
        assert body1["candles"][i]["close"] > body1["candles"][i - 1]["close"]

    # markers + equity_curve 시퀀스 동일
    assert body1["markers"] == body2["markers"]
    assert body1["equity_curve"] == body2["equity_curve"]
    # source/symbol/use_adjusted 등 메타 동일
    assert body1["source"] == body2["source"] == "daily_prices"
    assert body1["symbol"] == body2["symbol"] == "DETERM"


# ============================================================================
# 시나리오 4: chart-data use_adjusted toggle (13.7)
# ============================================================================
#
# 031 use_adjusted query option은 13.7 정책의 GUI 진입점. True (기본)이면 adj_*,
# False면 원 가격 (open/high/low/close).
#
# adj_close = close + adj_diff (시드)로 두 컬럼이 다른 값이도록 만들고
# toggle을 비교.


def test_phase12_chart_data_use_adjusted_toggle_uses_correct_columns(client, db_engine):
    sp = client.post("/api/strategies", json=_strategy_create_payload(name="adj-toggle")).json()
    bp = _backtest_payload(sp["id"], symbol="ADJTOG")
    run = client.post("/api/backtests", json=bp).json()

    _seed_daily_prices(
        db_engine, "ADJTOG", date(2024, 1, 2), n_days=10, base_close=10_000.0, adj_diff=500.0
    )

    body_adj = client.get(
        f"/api/backtests/{run['id']}/chart-data?use_adjusted=true"
    ).json()
    body_raw = client.get(
        f"/api/backtests/{run['id']}/chart-data?use_adjusted=false"
    ).json()

    # 둘 다 daily_prices 사용 + 같은 종목 + 같은 길이
    assert body_adj["source"] == body_raw["source"] == "daily_prices"
    assert body_adj["use_adjusted"] is True
    assert body_raw["use_adjusted"] is False
    assert len(body_adj["candles"]) == len(body_raw["candles"]) == 10

    # 13.7: adj close = raw close + 500 (시드 정의)
    for adj_c, raw_c in zip(body_adj["candles"], body_raw["candles"], strict=True):
        assert adj_c["time"] == raw_c["time"]
        assert adj_c["close"] == raw_c["close"] + 500.0
        assert adj_c["open"] == raw_c["open"] + 500.0


# ============================================================================
# 시나리오 5: chart-data fallback 분기 (DB 우선 → dev fallback → 운영 404)
# ============================================================================
#
# 031의 데이터 소스 우선순위:
#   1) daily_prices에 데이터 있음 → "daily_prices"
#   2) daily_prices 비어있음 + dev 모드 → "synthetic" fallback
#   3) daily_prices 비어있음 + 운영 모드 → 404 MARKET_DATA_NOT_FOUND
#
# 같은 run에 대해 daily_prices를 시드하기 전후 응답 source가 바뀌는지로
# fallback 분기가 e2e 동작하는지 검증 (단위 테스트는 분기별 격리).


def test_phase12_chart_data_fallback_chain_db_then_dev_then_404(
    client, db_engine, monkeypatch
):
    # dev 모드 (기본)에서 시작
    sp = client.post("/api/strategies", json=_strategy_create_payload(name="fallback")).json()
    bp = _backtest_payload(sp["id"], symbol="FB")
    run = client.post("/api/backtests", json=bp).json()

    # (b) daily_prices가 비어있고 dev 모드 → synthetic fallback
    body_dev = client.get(f"/api/backtests/{run['id']}/chart-data").json()
    assert body_dev["source"] == "synthetic"
    assert len(body_dev["candles"]) == 60  # synthetic_n=60

    # (a) daily_prices를 시드하면 즉시 우선순위 변경 (DB 우선)
    _seed_daily_prices(db_engine, "FB", date(2024, 1, 2), n_days=12)
    body_db = client.get(f"/api/backtests/{run['id']}/chart-data").json()
    assert body_db["source"] == "daily_prices"
    assert len(body_db["candles"]) == 12

    # (c) 운영 모드 + 다른 symbol에는 데이터 없음 → 404
    sp2 = client.post(
        "/api/strategies", json=_strategy_create_payload(name="fallback-prod")
    ).json()
    bp2 = _backtest_payload(sp2["id"], symbol="MISSING_PROD")
    run2 = client.post("/api/backtests", json=bp2).json()

    monkeypatch.setenv("APP_ENV", "production")
    r = client.get(f"/api/backtests/{run2['id']}/chart-data")
    assert r.status_code == 404, r.text
    body_404 = r.json()
    assert body_404["error"]["code"] == "MARKET_DATA_NOT_FOUND"
    # 표준 envelope 보존 (Phase 8 H7)
    assert "message" in body_404["error"]
