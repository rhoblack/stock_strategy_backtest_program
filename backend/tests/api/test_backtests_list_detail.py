"""GET /api/backtests 목록 + GET /api/backtests/{id} 상세 단위 테스트 (10-n).

테스트 항목:
- 목록 조회 (user_id scope, created_at DESC 정렬)
- status 필터
- strategy_id 필터
- 페이지네이션 메타 (page, page_size, total_count, total_pages, has_next)
- 단건 상세 (result 포함)
- 미존재/미소유 → 404
"""

from datetime import date


def _strategy_payload(name: str = "목록 테스트 전략") -> dict:
    return {
        "name": name,
        "description": "",
        "strategy_json": {
            "entry": {
                "logic": "AND",
                "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
            },
            "exit_position": {
                "logic": "OR",
                "conditions": [{"type": "stop_loss", "percent": 3.0}],
            },
        },
        "tags": [],
    }


def _backtest_payload(strategy_id: int, run_name: str = "test-run") -> dict:
    return {
        "strategy_id": strategy_id,
        "run_name": run_name,
        "universe_config": {
            "symbol": "GOLDEN",
            "position_size_amount": 5_000_000,
            "synthetic_seed": 42,
            "synthetic_n": 30,
        },
        "start_date": str(date(2024, 1, 2)),
        "end_date": str(date(2024, 3, 31)),
        "initial_cash": 10_000_000.0,
        "fee_rate": 0.0,
        "tax_rate": 0.0,
        "slippage": 0.0,
        "tick_rounding": "nearest",
    }


def test_list_empty(client):
    """실행 없으면 빈 목록 반환."""
    r = client.get("/api/backtests")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total_count"] == 0
    assert body["page"] == 1


def test_list_returns_run(client):
    """실행 후 목록에 포함된다."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()

    r = client.get("/api/backtests")
    assert r.status_code == 200
    body = r.json()
    assert body["total_count"] >= 1
    ids = [item["id"] for item in body["items"]]
    assert run["id"] in ids


def test_list_pagination_meta(client):
    """페이지네이션 메타가 올바르게 반환된다."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    # 실행 1개 생성
    client.post("/api/backtests", json=_backtest_payload(s["id"], "run1")).json()

    r = client.get("/api/backtests?page=1&page_size=10")
    assert r.status_code == 200
    body = r.json()
    assert "page" in body
    assert "page_size" in body
    assert "total_count" in body
    assert "total_pages" in body
    assert "has_next" in body
    assert body["page"] == 1
    assert body["page_size"] == 10


def test_list_filter_by_status(client):
    """status 필터가 동작한다."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()

    # completed 상태만 조회
    r_completed = client.get("/api/backtests?status=completed")
    assert r_completed.status_code == 200
    body = r_completed.json()
    # TestClient는 BackgroundTask를 동기 실행하므로 completed 상태
    ids_completed = [item["id"] for item in body["items"]]
    assert run["id"] in ids_completed

    # pending 상태만 — 없어야 함 (이미 completed)
    r_pending = client.get("/api/backtests?status=pending")
    assert r_pending.status_code == 200
    ids_pending = [item["id"] for item in r_pending.json()["items"]]
    assert run["id"] not in ids_pending


def test_list_filter_by_strategy_id(client):
    """strategy_id 필터가 동작한다."""
    s1 = client.post("/api/strategies", json=_strategy_payload("S1")).json()
    s2 = client.post("/api/strategies", json=_strategy_payload("S2")).json()
    run1 = client.post("/api/backtests", json=_backtest_payload(s1["id"], "r1")).json()
    run2 = client.post("/api/backtests", json=_backtest_payload(s2["id"], "r2")).json()

    r = client.get(f"/api/backtests?strategy_id={s1['id']}")
    assert r.status_code == 200
    body = r.json()
    ids = [item["id"] for item in body["items"]]
    assert run1["id"] in ids
    assert run2["id"] not in ids


def test_detail_returns_result(client):
    """완료된 백테스트 상세는 result 포함."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()
    run_id = run["id"]

    r = client.get(f"/api/backtests/{run_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == run_id
    assert body["status"] == "completed"
    # 완료된 경우 result 포함
    assert body["result"] is not None
    result = body["result"]
    assert "total_return_pct" in result
    assert "trade_count" in result
    assert "initial_cash" in result
    assert isinstance(result["initial_cash"], int)  # KRW 정수


def test_detail_includes_config_fields(client):
    """상세 응답에 tick_rounding / priority_method 등 설정 필드가 포함된다."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run = client.post("/api/backtests", json=_backtest_payload(s["id"])).json()
    run_id = run["id"]

    r = client.get(f"/api/backtests/{run_id}")
    assert r.status_code == 200
    body = r.json()
    assert "tick_rounding" in body
    assert "priority_method" in body
    assert "priority_tie_breaker" in body
    assert "use_adjusted_price" in body


def test_detail_not_found_returns_404(client):
    """미존재 run_id → 404 BACKTEST_RUN_NOT_FOUND."""
    r = client.get("/api/backtests/99999")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "BACKTEST_RUN_NOT_FOUND"
    assert "x-request-id" in {k.lower() for k in r.headers}


def test_list_created_at_desc_order(client):
    """목록은 created_at DESC 정렬이다."""
    s = client.post("/api/strategies", json=_strategy_payload()).json()
    run1 = client.post("/api/backtests", json=_backtest_payload(s["id"], "r1")).json()
    run2 = client.post("/api/backtests", json=_backtest_payload(s["id"], "r2")).json()

    r = client.get("/api/backtests")
    assert r.status_code == 200
    items = r.json()["items"]
    ids = [item["id"] for item in items]
    # run2가 나중에 생성됐으므로 앞에 와야 함 (DESC)
    assert ids.index(run2["id"]) < ids.index(run1["id"])
