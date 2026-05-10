"""Strategy CRUD API 테스트.

리뷰 011 이후:
    - exit_signal 또는 exit_position 중 하나가 필수가 됐기 때문에 페이로드를 보강.
    - 에러 응답은 표준 envelope `{"error": {...}}` 형식 — body["detail"]가 아닌
      body["error"]를 검증한다 (10번 7절).
"""


def _payload(name="테스트 전략") -> dict:
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
                "conditions": [
                    {"type": "stop_loss", "percent": 3.0},
                ],
            },
        },
        "tags": ["테스트"],
        "favorite": False,
    }


def test_create_and_list(client):
    r = client.post("/api/strategies", json=_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] > 0
    assert body["user_id"] == 1
    assert body["name"] == "테스트 전략"
    assert body["tags"] == ["테스트"]

    r2 = client.get("/api/strategies")
    assert r2.status_code == 200
    items = r2.json()
    assert len(items) == 1
    assert items[0]["id"] == body["id"]


def test_get_and_update(client):
    created = client.post("/api/strategies", json=_payload()).json()
    sid = created["id"]

    r = client.get(f"/api/strategies/{sid}")
    assert r.status_code == 200

    new_json = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [{"type": "stop_loss", "percent": 3.0}],
        },
    }
    r2 = client.put(
        f"/api/strategies/{sid}",
        json={"strategy_json": new_json, "change_note": "ma_period 20→5"},
    )
    assert r2.status_code == 200
    assert r2.json()["strategy_json"]["entry"]["conditions"][0]["ma_period"] == 5


def test_delete_soft(client):
    created = client.post("/api/strategies", json=_payload()).json()
    sid = created["id"]

    r = client.delete(f"/api/strategies/{sid}")
    assert r.status_code == 200
    assert r.json()["deleted_at"] is not None

    # 기본 list에서 안 보임
    items = client.get("/api/strategies").json()
    assert items == []

    # include_deleted=true 시 보임
    items_all = client.get("/api/strategies?include_deleted=true").json()
    assert len(items_all) == 1


def test_get_not_found_returns_404(client):
    r = client.get("/api/strategies/9999")
    assert r.status_code == 404
    body = r.json()
    # 표준 envelope (10번 7절)
    assert body["error"]["code"] == "STRATEGY_NOT_FOUND"
    assert "message" in body["error"]
    # X-Request-ID 헤더 (10번 8절)
    assert "x-request-id" in {k.lower() for k in r.headers}


def test_duplicate(client):
    created = client.post("/api/strategies", json=_payload("원본")).json()
    r = client.post(f"/api/strategies/{created['id']}/duplicate?new_name=복사본")
    assert r.status_code == 201
    dup = r.json()
    assert dup["id"] != created["id"]
    assert dup["name"] == "복사본"
    assert dup["favorite"] is False
