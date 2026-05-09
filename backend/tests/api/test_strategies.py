"""Strategy CRUD API 테스트."""


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
        }
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
    assert body["detail"]["code"] == "STRATEGY_NOT_FOUND"


def test_duplicate(client):
    created = client.post("/api/strategies", json=_payload("원본")).json()
    r = client.post(f"/api/strategies/{created['id']}/duplicate?new_name=복사본")
    assert r.status_code == 201
    dup = r.json()
    assert dup["id"] != created["id"]
    assert dup["name"] == "복사본"
    assert dup["favorite"] is False
