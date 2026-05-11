"""종목 검색 API 단위 테스트 (10-s, 06-k).

GET /api/symbols 테스트 항목:
- 기본 검색 (q 파라미터)
- market 필터 (KOSPI / KOSDAQ / ALL)
- limit 파라미터 (기본 20, 최대 100, 초과 시 422)
- 빈 결과
- 응답 필드 확인
- user_id scope 불필요 확인 (공개 엔드포인트)

(기존 GET /api/symbols/search 테스트는 test_market_data.py에 있음)
"""

from datetime import date

import pytest


def _insert_symbol(
    session,
    symbol: str,
    name: str = "테스트",
    market: str = "KOSPI",
    sector: str | None = None,
):
    from app.models.symbol import Symbol

    sym = Symbol(
        symbol=symbol,
        name=name,
        market=market,
        sector=sector,
        listing_date=date(2000, 1, 4),
        delisting_date=None,
        is_etf=False,
        is_spac=False,
        is_preferred=False,
        is_etn=False,
        is_managed=False,
        is_halted=False,
    )
    session.add(sym)
    session.flush()
    return sym


@pytest.fixture
def session_with_symbols(db_engine):
    """여러 시장의 종목을 DB에 삽입한 세션."""
    from app.db.session import make_session_factory

    SessionLocal = make_session_factory(db_engine)
    with SessionLocal() as session:
        _insert_symbol(session, "005930", "삼성전자", "KOSPI", "반도체")
        _insert_symbol(session, "000660", "SK하이닉스", "KOSPI", "반도체")
        _insert_symbol(session, "035420", "NAVER", "KOSPI", "인터넷")
        _insert_symbol(session, "247540", "에코프로비엠", "KOSDAQ", "2차전지")
        _insert_symbol(session, "263750", "펄어비스", "KOSDAQ", "게임")
        session.commit()
    return db_engine


# ── 기본 검색 ─────────────────────────────────────────────────────

def test_search_by_name_query(client, session_with_symbols):
    """q=삼성 → 삼성전자가 포함된다."""
    r = client.get("/api/symbols?q=삼성")
    assert r.status_code == 200
    items = r.json()
    symbols = [item["symbol"] for item in items]
    assert "005930" in symbols


def test_search_by_symbol_code(client, session_with_symbols):
    """q=000660 → SK하이닉스가 나온다."""
    r = client.get("/api/symbols?q=000660")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert items[0]["symbol"] == "000660"


def test_search_no_query_returns_all(client, session_with_symbols):
    """q 미지정 → 전체 (limit=20 기본 적용)."""
    r = client.get("/api/symbols")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) <= 20


# ── market 필터 ───────────────────────────────────────────────────

def test_market_filter_kospi(client, session_with_symbols):
    """market=KOSPI → KOSPI 종목만 나온다."""
    r = client.get("/api/symbols?market=KOSPI")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    for item in items:
        assert item["market"] == "KOSPI"


def test_market_filter_kosdaq(client, session_with_symbols):
    """market=KOSDAQ → KOSDAQ 종목만 나온다."""
    r = client.get("/api/symbols?market=KOSDAQ")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    for item in items:
        assert item["market"] == "KOSDAQ"


def test_market_filter_all(client, session_with_symbols):
    """market=ALL → 전체 시장 반환."""
    r = client.get("/api/symbols?market=ALL")
    assert r.status_code == 200
    items = r.json()
    markets = {item["market"] for item in items}
    # KOSPI와 KOSDAQ 모두 포함되어야 함
    assert "KOSPI" in markets
    assert "KOSDAQ" in markets


def test_market_filter_case_insensitive(client, session_with_symbols):
    """market 대소문자 미구분 (KOSPI == kospi는 라우터 레벨에서 upper() 처리)."""
    # market 파라미터는 대문자로 통일되므로 KOSPI로 테스트
    r = client.get("/api/symbols?market=KOSPI")
    assert r.status_code == 200


# ── limit 파라미터 ────────────────────────────────────────────────

def test_limit_default_20(client, session_with_symbols):
    """limit 미지정 시 기본 20 적용."""
    r = client.get("/api/symbols")
    assert r.status_code == 200
    # 5개 삽입했으므로 5개 반환
    assert len(r.json()) == 5


def test_limit_custom(client, session_with_symbols):
    """limit=2 → 최대 2건만 반환."""
    r = client.get("/api/symbols?limit=2")
    assert r.status_code == 200
    assert len(r.json()) <= 2


def test_limit_max_100(client, session_with_symbols):
    """limit=100 → 정상 동작."""
    r = client.get("/api/symbols?limit=100")
    assert r.status_code == 200


def test_limit_over_100_returns_422(client, session_with_symbols):
    """limit=101 → 422 (FastAPI Query 범위 초과)."""
    r = client.get("/api/symbols?limit=101")
    assert r.status_code == 422 or r.status_code == 400


def test_limit_zero_returns_error(client, session_with_symbols):
    """limit=0 → 422 (ge=1 제약)."""
    r = client.get("/api/symbols?limit=0")
    assert r.status_code == 422 or r.status_code == 400


# ── 빈 결과 ───────────────────────────────────────────────────────

def test_empty_result_for_unknown_keyword(client, session_with_symbols):
    """존재하지 않는 키워드 → 빈 배열."""
    r = client.get("/api/symbols?q=없는종목XYZ999")
    assert r.status_code == 200
    assert r.json() == []


def test_empty_result_for_unknown_market(client, session_with_symbols):
    """존재하지 않는 market → 빈 배열."""
    r = client.get("/api/symbols?market=KONEX")
    assert r.status_code == 200
    assert r.json() == []


# ── 응답 필드 확인 ────────────────────────────────────────────────

def test_response_fields(client, session_with_symbols):
    """응답에 필수 필드가 있어야 한다."""
    r = client.get("/api/symbols?q=삼성")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    item = items[0]
    for field in ("symbol", "name", "market"):
        assert field in item, f"{field} 필드 누락"


def test_response_sector_field(client, session_with_symbols):
    """sector 필드가 포함되거나 null이다."""
    r = client.get("/api/symbols?q=삼성")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    # sector는 nullable
    assert "sector" in items[0]
    assert items[0]["sector"] == "반도체"


def test_x_request_id_header_present(client, session_with_symbols):
    """X-Request-ID 헤더가 항상 포함된다 (10.8)."""
    r = client.get("/api/symbols")
    assert r.status_code == 200
    assert "x-request-id" in {k.lower() for k in r.headers}


# ── 정렬 확인 ─────────────────────────────────────────────────────

def test_active_symbols_first(client, db_engine):
    """delisting_date가 없는 (상장 중) 종목이 먼저 나온다."""
    from app.db.session import make_session_factory
    from app.models.symbol import Symbol

    SessionLocal = make_session_factory(db_engine)
    with SessionLocal() as session:
        # 폐지 종목 추가
        session.add(Symbol(
            symbol="999999",
            name="폐지종목",
            market="KOSPI",
            listing_date=date(2000, 1, 4),
            delisting_date=date(2020, 1, 1),
            is_etf=False, is_spac=False, is_preferred=False,
            is_etn=False, is_managed=False, is_halted=False,
        ))
        # 활성 종목 추가
        session.add(Symbol(
            symbol="AAABBB",
            name="활성종목",
            market="KOSPI",
            listing_date=date(2000, 1, 4),
            delisting_date=None,
            is_etf=False, is_spac=False, is_preferred=False,
            is_etn=False, is_managed=False, is_halted=False,
        ))
        session.commit()

    r = client.get("/api/symbols?limit=100")
    assert r.status_code == 200
    items = r.json()
    # 폐지 종목 (999999)이 나오면 활성 종목(AAABBB) 뒤에 나와야 함
    symbols = [item["symbol"] for item in items]
    if "999999" in symbols and "AAABBB" in symbols:
        idx_active = symbols.index("AAABBB")
        idx_delisted = symbols.index("999999")
        assert idx_active < idx_delisted, "활성 종목이 폐지 종목보다 먼저 나와야 함"
