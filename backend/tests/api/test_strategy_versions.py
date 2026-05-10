"""GET /api/strategies/{id}/versions 단위 테스트 (10-m).

테스트 항목:
- 버전 목록 조회 (초기 버전 1개)
- 수정 후 버전 증가 확인
- 존재하지 않는 전략 → 404 STRATEGY_NOT_FOUND
- strategy_json_summary 필드 포함 확인
"""


def _strategy_payload(name: str = "버전 테스트 전략") -> dict:
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
        "tags": [],
        "favorite": False,
    }


def test_versions_initial_has_one(client):
    """전략 생성 시 version=1 이 자동 생성된다."""
    created = client.post("/api/strategies", json=_strategy_payload()).json()
    sid = created["id"]

    r = client.get(f"/api/strategies/{sid}/versions")
    assert r.status_code == 200
    versions = r.json()
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["strategy_id"] == sid


def test_versions_increases_after_update(client):
    """strategy_json 변경 시 버전이 증가한다."""
    created = client.post("/api/strategies", json=_strategy_payload()).json()
    sid = created["id"]

    new_json = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [{"type": "stop_loss", "percent": 2.0}],
        },
    }
    client.put(f"/api/strategies/{sid}", json={"strategy_json": new_json, "change_note": "ma_period 변경"})

    r = client.get(f"/api/strategies/{sid}/versions")
    assert r.status_code == 200
    versions = r.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 1
    assert versions[1]["version_number"] == 2
    # 변경 노트 보존
    assert versions[1]["change_note"] == "ma_period 변경"


def test_versions_summary_contains_condition_counts(client):
    """strategy_json_summary에 조건 개수 정보가 포함된다."""
    created = client.post("/api/strategies", json=_strategy_payload()).json()
    sid = created["id"]

    r = client.get(f"/api/strategies/{sid}/versions")
    assert r.status_code == 200
    summary = r.json()[0]["strategy_json_summary"]
    assert "entry_condition_count" in summary
    assert summary["entry_condition_count"] == 1
    assert "exit_position_condition_count" in summary
    assert summary["exit_position_condition_count"] == 1


def test_versions_not_found_returns_404(client):
    """존재하지 않는 전략의 버전 조회 → 404 STRATEGY_NOT_FOUND."""
    r = client.get("/api/strategies/99999/versions")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "STRATEGY_NOT_FOUND"
    # X-Request-ID 헤더 (10번 8절)
    assert "x-request-id" in {k.lower() for k in r.headers}


def test_versions_no_change_on_metadata_update(client):
    """name/description/tags만 변경하면 버전이 추가되지 않는다."""
    created = client.post("/api/strategies", json=_strategy_payload()).json()
    sid = created["id"]

    client.put(f"/api/strategies/{sid}", json={"name": "새 이름"})

    r = client.get(f"/api/strategies/{sid}/versions")
    assert r.status_code == 200
    # name만 변경 — json 변경 없으므로 버전 추가 안됨
    assert len(r.json()) == 1
