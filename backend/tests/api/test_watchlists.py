"""관심종목(Watchlist) API 단위 테스트 (10-t, 07-q).

테스트 항목:
- POST /api/watchlists — 그룹 생성
- GET  /api/watchlists — 목록 조회 (user_id scope)
- GET  /api/watchlists/{id} — 상세 조회
- POST /api/watchlists/{id}/symbols — 종목 추가
- DELETE /api/watchlists/{id}/symbols/{sym} — 종목 제거
- DELETE /api/watchlists/{id} — 그룹 삭제

보안 (10.9 user_id scope):
- 다른 user 소유 watchlist 접근 시 404 WATCHLIST_NOT_FOUND
- user_id=1 고정(MVP) 이므로 직접 DB에 user_id=2 row 삽입하여 테스트

에러 코드 (10번 §7.1):
- WATCHLIST_NOT_FOUND (404)
- WATCHLIST_ITEM_ALREADY_EXISTS (409)
"""




# ── 헬퍼 ──────────────────────────────────────────────────────────

def _create_watchlist(client, name: str = "내 관심종목", description: str = "") -> dict:
    """POST /api/watchlists 헬퍼."""
    r = client.post("/api/watchlists", json={"name": name, "description": description})
    assert r.status_code == 201, r.text
    return r.json()


def _insert_watchlist_for_other_user(db_engine, name: str = "다른유저 관심종목") -> int:
    """user_id=2 소유 watchlist를 직접 DB에 삽입. 반환값은 watchlist id."""
    from app.db.session import make_session_factory
    from app.models.user import User
    from app.models.watchlist import Watchlist

    SessionLocal = make_session_factory(db_engine)
    with SessionLocal() as session:
        # user_id=2 존재 확인 / 생성
        if session.get(User, 2) is None:
            session.add(User(id=2, email="other@local"))
            session.flush()

        wl = Watchlist(user_id=2, name=name, description="")
        session.add(wl)
        session.flush()
        wl_id = wl.id
        session.commit()
    return wl_id


# ── POST /api/watchlists ──────────────────────────────────────────

def test_create_watchlist(client, db_engine):
    """그룹 생성 → 201 + WatchlistOut."""
    r = client.post("/api/watchlists", json={"name": "기술주", "description": "반도체/인터넷"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "기술주"
    assert body["description"] == "반도체/인터넷"
    assert "id" in body
    assert body["user_id"] == 1  # MVP user_id=1


def test_create_watchlist_minimal(client, db_engine):
    """name만 있어도 생성 가능 (description 기본값 '')."""
    r = client.post("/api/watchlists", json={"name": "최소입력"})
    assert r.status_code == 201
    assert r.json()["description"] == ""


def test_create_watchlist_missing_name_returns_error(client, db_engine):
    """name 누락 → 400 에러 (표준 envelope)."""
    r = client.post("/api/watchlists", json={"description": "name 없음"})
    assert r.status_code in (400, 422)
    body = r.json()
    assert "error" in body


def test_create_watchlist_name_too_long_returns_error(client, db_engine):
    """name 101자 → 422."""
    r = client.post("/api/watchlists", json={"name": "a" * 101})
    assert r.status_code in (400, 422)


def test_create_watchlist_x_request_id(client, db_engine):
    """응답에 X-Request-ID 헤더가 있어야 한다 (10.8)."""
    r = client.post("/api/watchlists", json={"name": "헤더테스트"})
    assert r.status_code == 201
    assert "x-request-id" in {k.lower() for k in r.headers}


# ── GET /api/watchlists ───────────────────────────────────────────

def test_list_watchlists_empty(client, db_engine):
    """watchlist 없는 상태에서 조회 → 빈 배열."""
    r = client.get("/api/watchlists")
    assert r.status_code == 200
    assert r.json() == []


def test_list_watchlists_returns_own(client, db_engine):
    """본인 그룹만 반환된다 (user_id=1)."""
    _create_watchlist(client, "그룹A")
    _create_watchlist(client, "그룹B")
    r = client.get("/api/watchlists")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    names = {item["name"] for item in items}
    assert "그룹A" in names
    assert "그룹B" in names


def test_list_watchlists_scope_excludes_other_user(client, db_engine):
    """다른 user(user_id=2)의 그룹은 목록에 나오지 않는다."""
    _insert_watchlist_for_other_user(db_engine, "타인그룹")
    _create_watchlist(client, "내그룹")

    r = client.get("/api/watchlists")
    assert r.status_code == 200
    items = r.json()
    names = {item["name"] for item in items}
    assert "타인그룹" not in names
    assert "내그룹" in names


def test_list_watchlists_item_count_field(client, db_engine):
    """item_count 필드가 있다."""
    _create_watchlist(client, "카운트테스트")
    r = client.get("/api/watchlists")
    assert r.status_code == 200
    item = r.json()[0]
    assert "item_count" in item
    assert item["item_count"] == 0


# ── GET /api/watchlists/{id} ──────────────────────────────────────

def test_get_watchlist_detail(client, db_engine):
    """상세 조회 → items 필드 포함."""
    wl = _create_watchlist(client, "상세테스트")
    r = client.get(f"/api/watchlists/{wl['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == wl["id"]
    assert body["name"] == "상세테스트"
    assert isinstance(body["items"], list)


def test_get_watchlist_other_user_returns_404(client, db_engine):
    """다른 user 소유 watchlist 조회 → 404 WATCHLIST_NOT_FOUND."""
    other_id = _insert_watchlist_for_other_user(db_engine)
    r = client.get(f"/api/watchlists/{other_id}")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "WATCHLIST_NOT_FOUND"


def test_get_watchlist_nonexistent_returns_404(client, db_engine):
    """존재하지 않는 id → 404 WATCHLIST_NOT_FOUND."""
    r = client.get("/api/watchlists/99999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "WATCHLIST_NOT_FOUND"


# ── POST /api/watchlists/{id}/symbols ────────────────────────────

def test_add_symbol(client, db_engine):
    """종목 추가 → 201 + WatchlistItemOut."""
    wl = _create_watchlist(client, "종목추가테스트")
    r = client.post(f"/api/watchlists/{wl['id']}/symbols", json={"symbol": "005930"})
    assert r.status_code == 201
    body = r.json()
    assert body["symbol"] == "005930"
    assert body["watchlist_id"] == wl["id"]
    assert "id" in body
    assert "added_at" in body


def test_add_symbol_reflects_in_detail(client, db_engine):
    """추가 후 상세 조회 시 items에 포함된다."""
    wl = _create_watchlist(client, "items확인")
    client.post(f"/api/watchlists/{wl['id']}/symbols", json={"symbol": "005930"})
    client.post(f"/api/watchlists/{wl['id']}/symbols", json={"symbol": "000660"})

    r = client.get(f"/api/watchlists/{wl['id']}")
    assert r.status_code == 200
    symbols = [it["symbol"] for it in r.json()["items"]]
    assert "005930" in symbols
    assert "000660" in symbols


def test_add_symbol_updates_item_count(client, db_engine):
    """종목 추가 후 목록의 item_count가 증가한다."""
    wl = _create_watchlist(client, "카운트증가")
    client.post(f"/api/watchlists/{wl['id']}/symbols", json={"symbol": "005930"})

    r = client.get("/api/watchlists")
    item = next(it for it in r.json() if it["id"] == wl["id"])
    assert item["item_count"] == 1


def test_add_symbol_duplicate_returns_409(client, db_engine):
    """동일 종목 중복 추가 → 409 WATCHLIST_ITEM_ALREADY_EXISTS."""
    wl = _create_watchlist(client, "중복테스트")
    client.post(f"/api/watchlists/{wl['id']}/symbols", json={"symbol": "005930"})
    r = client.post(f"/api/watchlists/{wl['id']}/symbols", json={"symbol": "005930"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "WATCHLIST_ITEM_ALREADY_EXISTS"


def test_add_symbol_other_user_watchlist_returns_404(client, db_engine):
    """다른 user watchlist에 종목 추가 → 404."""
    other_id = _insert_watchlist_for_other_user(db_engine)
    r = client.post(f"/api/watchlists/{other_id}/symbols", json={"symbol": "005930"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "WATCHLIST_NOT_FOUND"


def test_add_symbol_missing_symbol_returns_error(client, db_engine):
    """symbol 누락 → 422."""
    wl = _create_watchlist(client, "필드누락")
    r = client.post(f"/api/watchlists/{wl['id']}/symbols", json={})
    assert r.status_code in (400, 422)


# ── DELETE /api/watchlists/{id}/symbols/{symbol} ─────────────────

def test_remove_symbol(client, db_engine):
    """종목 제거 → 204 No Content."""
    wl = _create_watchlist(client, "종목제거테스트")
    client.post(f"/api/watchlists/{wl['id']}/symbols", json={"symbol": "005930"})
    r = client.delete(f"/api/watchlists/{wl['id']}/symbols/005930")
    assert r.status_code == 204


def test_remove_symbol_not_in_list_returns_204(client, db_engine):
    """없는 종목 제거 → idempotent, 204 반환."""
    wl = _create_watchlist(client, "없는종목제거")
    r = client.delete(f"/api/watchlists/{wl['id']}/symbols/999999")
    assert r.status_code == 204


def test_remove_symbol_reflects_in_detail(client, db_engine):
    """제거 후 상세 조회 시 items에 없어야 한다."""
    wl = _create_watchlist(client, "제거후확인")
    client.post(f"/api/watchlists/{wl['id']}/symbols", json={"symbol": "005930"})
    client.delete(f"/api/watchlists/{wl['id']}/symbols/005930")

    r = client.get(f"/api/watchlists/{wl['id']}")
    symbols = [it["symbol"] for it in r.json()["items"]]
    assert "005930" not in symbols


def test_remove_symbol_other_user_watchlist_returns_404(client, db_engine):
    """다른 user watchlist에서 종목 제거 → 404."""
    other_id = _insert_watchlist_for_other_user(db_engine)
    r = client.delete(f"/api/watchlists/{other_id}/symbols/005930")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "WATCHLIST_NOT_FOUND"


# ── DELETE /api/watchlists/{id} ───────────────────────────────────

def test_delete_watchlist(client, db_engine):
    """그룹 삭제 → 204."""
    wl = _create_watchlist(client, "삭제테스트")
    r = client.delete(f"/api/watchlists/{wl['id']}")
    assert r.status_code == 204


def test_delete_watchlist_cascade_items(client, db_engine):
    """그룹 삭제 시 items도 함께 삭제된다 (cascade)."""
    wl = _create_watchlist(client, "cascade삭제")
    client.post(f"/api/watchlists/{wl['id']}/symbols", json={"symbol": "005930"})

    # 삭제
    r = client.delete(f"/api/watchlists/{wl['id']}")
    assert r.status_code == 204

    # 삭제 후 조회 → 404
    r2 = client.get(f"/api/watchlists/{wl['id']}")
    assert r2.status_code == 404


def test_delete_watchlist_gone_from_list(client, db_engine):
    """삭제 후 목록에서 사라진다."""
    wl = _create_watchlist(client, "목록에서제거")
    client.delete(f"/api/watchlists/{wl['id']}")

    r = client.get("/api/watchlists")
    ids = [item["id"] for item in r.json()]
    assert wl["id"] not in ids


def test_delete_watchlist_other_user_returns_404(client, db_engine):
    """다른 user watchlist 삭제 → 404 WATCHLIST_NOT_FOUND."""
    other_id = _insert_watchlist_for_other_user(db_engine)
    r = client.delete(f"/api/watchlists/{other_id}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "WATCHLIST_NOT_FOUND"


def test_delete_nonexistent_watchlist_returns_404(client, db_engine):
    """존재하지 않는 id 삭제 → 404."""
    r = client.delete("/api/watchlists/99999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "WATCHLIST_NOT_FOUND"


# ── 에러 envelope 표준 확인 ───────────────────────────────────────

def test_error_response_envelope_structure(client, db_engine):
    """404 에러 응답이 표준 envelope 형식이어야 한다 (10.7)."""
    r = client.get("/api/watchlists/99999")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    err = body["error"]
    assert "code" in err
    assert "message" in err
    assert "details" in err
    assert isinstance(err["details"], list)


def test_error_response_has_x_request_id(client, db_engine):
    """에러 응답에도 X-Request-ID 헤더가 있어야 한다 (10.8)."""
    r = client.get("/api/watchlists/99999")
    assert r.status_code == 404
    assert "x-request-id" in {k.lower() for k in r.headers}
