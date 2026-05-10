"""user_id 스코프 강제 (10번 9절) + 표준 error envelope (10번 7절) +
X-Request-ID (10번 8절) 통합 테스트.

리뷰 011 Critical 3건의 회귀 방지:
    - C3: get/update/delete/duplicate가 모두 user_id를 받고, 미소유 자원에
      접근하면 STRATEGY_NOT_FOUND (404) — 존재 여부조차 노출 금지.
    - H7: 모든 에러 응답이 `{"error": {...}}` envelope이며 X-Request-ID
      헤더가 부착됨.

여기서는 dependency_overrides로 인증된 user_id를 바꿔가며 테스트한다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user_id
from app.main import app
from app.models.user import User


def _strategy_payload(name: str = "전략1") -> dict:
    return {
        "name": name,
        "description": "",
        "strategy_json": {
            "entry": {
                "logic": "AND",
                "conditions": [
                    {"type": "price_vs_ma", "ma_period": 20, "operator": ">"},
                ],
            },
            "exit_position": {
                "logic": "OR",
                "conditions": [{"type": "stop_loss", "percent": 3.0}],
            },
        },
        "tags": [],
    }


@pytest.fixture
def two_users(db_engine):  # noqa: ARG001
    """user_id=1 (이미 conftest가 만듦) + user_id=2 추가."""
    from app.db.session import make_session_factory
    from app.main_state import get_engine

    SessionLocal = make_session_factory(get_engine())
    with SessionLocal() as session:
        if session.get(User, 2) is None:
            session.add(User(id=2, email="other@local"))
            session.commit()


@pytest.fixture
def client_as_user(two_users):  # noqa: ARG001
    """user_id를 갈아끼울 수 있는 client 팩토리.

    dependency_overrides는 app 전역이라 한 시점에 한 user만 활성화된다.
    `client_as_user(N)`을 호출하면 그 시점부터 user_id=N으로 인증된 채 동작.
    같은 테스트 안에서 user를 바꾸려면 다시 `client_as_user(M)`을 호출해
    새 클라이언트를 받는다 (이전 client도 새 user_id로 동작 — 같은 app이므로).
    """

    def _make_client(user_id: int) -> TestClient:
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        return TestClient(app)

    yield _make_client
    app.dependency_overrides.clear()


# ============================================================================
# C3 user_id scope — strategy
# ============================================================================


def test_user2_cannot_get_user1_strategy(client_as_user):
    # user 1으로 strategy 생성
    client = client_as_user(1)
    created = client.post("/api/strategies", json=_strategy_payload()).json()
    sid = created["id"]

    # user 2로 전환 후 조회 시도
    client = client_as_user(2)
    r = client.get(f"/api/strategies/{sid}")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "STRATEGY_NOT_FOUND"


def test_user2_cannot_update_user1_strategy(client_as_user):
    client = client_as_user(1)
    created = client.post("/api/strategies", json=_strategy_payload()).json()
    sid = created["id"]

    new_json = _strategy_payload("rename")["strategy_json"]
    client = client_as_user(2)
    r = client.put(f"/api/strategies/{sid}", json={"strategy_json": new_json})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "STRATEGY_NOT_FOUND"

    # user 1로 다시 전환 — 원본은 변경 안 됨
    client = client_as_user(1)
    after = client.get(f"/api/strategies/{sid}").json()
    assert after["name"] == "전략1"


def test_user2_cannot_delete_user1_strategy(client_as_user):
    client = client_as_user(1)
    created = client.post("/api/strategies", json=_strategy_payload()).json()
    sid = created["id"]

    client = client_as_user(2)
    r = client.delete(f"/api/strategies/{sid}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "STRATEGY_NOT_FOUND"

    # user 1로 전환 — 원본은 살아있음
    client = client_as_user(1)
    assert client.get(f"/api/strategies/{sid}").status_code == 200


def test_user2_cannot_duplicate_user1_strategy(client_as_user):
    """duplicate가 src.user_id를 그대로 쓰면 user2가 user1의 전략을
    자기 명의로 복사하는 권한 escalation 가능 — 막아야 한다."""
    client = client_as_user(1)
    created = client.post("/api/strategies", json=_strategy_payload()).json()
    sid = created["id"]

    client = client_as_user(2)
    r = client.post(f"/api/strategies/{sid}/duplicate?new_name=훔친것")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "STRATEGY_NOT_FOUND"

    # user 2의 strategies 리스트에 새 사본이 생성되지 않음
    user2_list = client.get("/api/strategies").json()
    assert user2_list == []


def test_list_strategies_only_returns_own(client_as_user):
    client = client_as_user(1)
    client.post("/api/strategies", json=_strategy_payload("user1's"))

    client = client_as_user(2)
    client.post("/api/strategies", json=_strategy_payload("user2's"))

    # 각자 본인 것만 보임
    client = client_as_user(1)
    user1_list = client.get("/api/strategies").json()
    client = client_as_user(2)
    user2_list = client.get("/api/strategies").json()
    assert {s["name"] for s in user1_list} == {"user1's"}
    assert {s["name"] for s in user2_list} == {"user2's"}


# ============================================================================
# C3 user_id scope — backtest
# ============================================================================


def _backtest_payload(strategy_id: int) -> dict:
    from datetime import date

    return {
        "strategy_id": strategy_id,
        "run_name": "scope test",
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


def _make_run_as_user1(client_as_user) -> int:
    client = client_as_user(1)
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()
    return run["id"]


def test_user2_cannot_get_user1_backtest_status(client_as_user):
    run_id = _make_run_as_user1(client_as_user)
    client = client_as_user(2)
    r = client.get(f"/api/backtests/{run_id}/status")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "BACKTEST_RUN_NOT_FOUND"


def test_user2_cannot_get_user1_backtest_summary(client_as_user):
    run_id = _make_run_as_user1(client_as_user)
    client = client_as_user(2)
    r = client.get(f"/api/backtests/{run_id}/summary")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "BACKTEST_RUN_NOT_FOUND"


def test_user2_cannot_export_user1_backtest(client_as_user):
    run_id = _make_run_as_user1(client_as_user)
    client = client_as_user(2)
    r = client.get(f"/api/backtests/{run_id}/export/zip")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "BACKTEST_RUN_NOT_FOUND"


def test_user2_cannot_cancel_user1_backtest(client_as_user):
    run_id = _make_run_as_user1(client_as_user)
    client = client_as_user(2)
    r = client.post(f"/api/backtests/{run_id}/cancel")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "BACKTEST_RUN_NOT_FOUND"


def test_user2_cannot_get_user1_backtest_trades(client_as_user):
    run_id = _make_run_as_user1(client_as_user)
    client = client_as_user(2)
    r = client.get(f"/api/backtests/{run_id}/trades")
    assert r.status_code == 404


def test_user2_cannot_get_user1_backtest_chart_data(client_as_user):
    run_id = _make_run_as_user1(client_as_user)
    client = client_as_user(2)
    r = client.get(f"/api/backtests/{run_id}/chart-data")
    assert r.status_code == 404


def test_user2_cannot_get_user1_backtest_daily_equity(client_as_user):
    run_id = _make_run_as_user1(client_as_user)
    client = client_as_user(2)
    r = client.get(f"/api/backtests/{run_id}/daily-equity")
    assert r.status_code == 404


def test_user2_cannot_get_user1_backtest_cash_events(client_as_user):
    run_id = _make_run_as_user1(client_as_user)
    client = client_as_user(2)
    r = client.get(f"/api/backtests/{run_id}/cash-events")
    assert r.status_code == 404


# ============================================================================
# H7 envelope + X-Request-ID
# ============================================================================


def test_all_error_responses_use_envelope(client_as_user):
    """다양한 에러 케이스가 모두 {"error": {...}} 형식을 따른다."""
    client = client_as_user(1)

    # 404 — 존재하지 않는 strategy
    r = client.get("/api/strategies/9999")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body and "detail" not in body
    assert {"code", "message", "details"} <= set(body["error"].keys())

    # 404 — 존재하지 않는 backtest
    r = client.get("/api/backtests/9999/status")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "BACKTEST_RUN_NOT_FOUND"

    # 422 — 포지션 조건이 entry에 들어감
    bad_payload = _strategy_payload()
    bad_payload["strategy_json"]["entry"]["conditions"].append(
        {"type": "stop_loss", "percent": 3.0}
    )
    r = client.post("/api/strategies", json=bad_payload)
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "EXIT_POSITION_IN_EXIT_SIGNAL"

    # 422 — 알 수 없는 condition type
    bad2 = _strategy_payload()
    bad2["strategy_json"]["entry"]["conditions"][0]["type"] = "no_such"
    r = client.post("/api/strategies", json=bad2)
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "UNKNOWN_CONDITION_TYPE"

    # 400 — 시계열 조건이 exit_position에
    bad3 = _strategy_payload()
    bad3["strategy_json"]["exit_position"]["conditions"] = [
        {"type": "price_vs_ma", "ma_period": 20, "operator": "<"}
    ]
    r = client.post("/api/strategies", json=bad3)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "EXIT_SIGNAL_IN_EXIT_POSITION"

    # 400 — entry 누락
    bad4 = _strategy_payload()
    bad4["strategy_json"].pop("entry")
    r = client.post("/api/strategies", json=bad4)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_STRATEGY_JSON"


def test_x_request_id_present_on_success(client_as_user):
    client = client_as_user(1)
    r = client.get("/api/conditions")
    assert r.status_code == 200
    assert "x-request-id" in {k.lower() for k in r.headers}


def test_x_request_id_present_on_error(client_as_user):
    client = client_as_user(1)
    r = client.get("/api/strategies/9999")
    assert r.status_code == 404
    assert "x-request-id" in {k.lower() for k in r.headers}


def test_x_request_id_preserves_incoming_value(client_as_user):
    """incoming X-Request-ID를 그대로 보존."""
    client = client_as_user(1)
    r = client.get(
        "/api/conditions", headers={"X-Request-ID": "my-trace-id-abc"}
    )
    assert r.status_code == 200
    assert r.headers["X-Request-ID"] == "my-trace-id-abc"


def test_x_request_id_preserves_incoming_on_error(client_as_user):
    """에러 응답도 incoming Request-ID 보존."""
    client = client_as_user(1)
    r = client.get(
        "/api/strategies/9999", headers={"X-Request-ID": "trace-on-error"}
    )
    assert r.status_code == 404
    assert r.headers["X-Request-ID"] == "trace-on-error"


def test_x_request_id_generated_when_absent(client_as_user):
    """incoming 헤더가 없으면 새 ID를 발급."""
    client = client_as_user(1)
    r = client.get("/api/conditions")
    rid = r.headers.get("X-Request-ID")
    assert rid
    # uuid4().hex은 32자
    assert len(rid) >= 8


def test_invalid_json_body_returns_envelope(client_as_user):
    """Pydantic schema 위반(필수 필드 누락 등)도 envelope으로."""
    client = client_as_user(1)
    # name 누락 — Pydantic이 거부
    r = client.post("/api/strategies", json={"strategy_json": {}})
    assert r.status_code == 400
    body = r.json()
    assert "error" in body and "detail" not in body


# ============================================================================
# 백테스트 생성 시점 strategy_json 재검증 (validator가 큐 진입 전 한 번 더)
# ============================================================================


def test_backtest_create_with_invalid_existing_strategy(client_as_user, db_engine):  # noqa: ARG001
    """이미 저장된 (원래 통과했던) strategy가 정책 변경 등으로 invalid 상태가
    됐다고 가정 — backtest 생성 시 한번 더 검증되어 차단되는지.

    여기서는 DB에 직접 invalid strategy를 만들고 backtest 시도.
    """
    from app.db.session import make_session_factory
    from app.main_state import get_engine
    from app.models.strategy import Strategy

    SessionLocal = make_session_factory(get_engine())
    with SessionLocal() as session:
        s = Strategy(
            user_id=1,
            name="legacy invalid",
            description="",
            strategy_json={
                # entry 누락 — validator가 거부
                "exit_position": {
                    "logic": "OR",
                    "conditions": [{"type": "stop_loss", "percent": 3.0}],
                }
            },
            tags=[],
            favorite=False,
        )
        session.add(s)
        session.commit()
        session.refresh(s)
        sid = s.id

    client = client_as_user(1)
    r = client.post("/api/backtests", json=_backtest_payload(sid))
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "INVALID_STRATEGY_JSON"
