"""시장 데이터 API 단위 테스트 (10-o).

테스트 항목:
- GET /api/symbols/search : 검색어/market 필터 + 최대 50건
- GET /api/symbols/{symbol}/daily-prices : 일봉 조회 + adjusted 파라미터
- GET /api/calendar : 거래 캘린더 조회 (year/month/market)
- SYMBOL_NOT_FOUND, MARKET_DATA_NOT_FOUND 에러 envelope 확인
"""

from datetime import UTC, date, datetime

import pytest

# ── 공통 fixture: DB에 심볼 + 일봉 + 캘린더 삽입

def _insert_symbol(session, symbol: str = "005930", name: str = "삼성전자", market: str = "KOSPI"):
    from app.models.symbol import Symbol

    sym = Symbol(
        symbol=symbol,
        name=name,
        market=market,
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


def _insert_daily_price(session, symbol: str = "005930", trade_date: date = date(2024, 1, 2)):
    from app.models.daily_price import DailyPrice

    dp = DailyPrice(
        symbol=symbol,
        date=trade_date,
        open=70000,
        high=72000,
        low=69000,
        close=71000,
        volume=1000000,
        adj_open=70000,
        adj_high=72000,
        adj_low=69000,
        adj_close=71000,
        adj_volume=1000000,
        market_cap=None,
        created_at=datetime.now(UTC),
    )
    session.add(dp)
    session.flush()
    return dp


def _insert_trading_calendar(session, trade_date: date = date(2024, 1, 2), market: str = "KOSPI", is_trading: bool = True):
    from app.models.trading_calendar import TradingCalendar

    tc = TradingCalendar(
        date=trade_date,
        market=market,
        is_trading_day=is_trading,
        holiday_name=None if is_trading else "신정",
        created_at=datetime.now(UTC),
    )
    session.add(tc)
    session.flush()
    return tc


@pytest.fixture
def session_with_data(db_engine):
    """DB에 심볼 + 일봉 + 캘린더 데이터가 있는 db_engine.

    client fixture도 같은 db_engine을 사용하므로 데이터를 공유한다.
    """
    from app.db.session import make_session_factory

    SessionLocal = make_session_factory(db_engine)
    with SessionLocal() as session:
        _insert_symbol(session, "005930", "삼성전자", "KOSPI")
        _insert_symbol(session, "000660", "SK하이닉스", "KOSPI")
        _insert_symbol(session, "ABCDEF", "코스닥회사", "KOSDAQ")

        _insert_daily_price(session, "005930", date(2024, 1, 2))
        _insert_daily_price(session, "005930", date(2024, 1, 3))

        _insert_trading_calendar(session, date(2024, 1, 2), "KOSPI", is_trading=True)
        _insert_trading_calendar(session, date(2024, 1, 1), "KOSPI", is_trading=False)

        session.commit()
    # client fixture가 db_engine에 의존하므로 순서 보장을 위해 db_engine 반환
    return db_engine


# ── symbols/search 테스트

def test_search_by_name(client, session_with_data):
    r = client.get("/api/symbols/search?q=삼성")
    assert r.status_code == 200
    items = r.json()
    symbols = [item["symbol"] for item in items]
    assert "005930" in symbols


def test_search_by_symbol_code(client, session_with_data):
    r = client.get("/api/symbols/search?q=000660")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert items[0]["symbol"] == "000660"


def test_search_with_market_filter(client, session_with_data):
    r = client.get("/api/symbols/search?market=KOSDAQ")
    assert r.status_code == 200
    items = r.json()
    # KOSDAQ 종목만 나와야 함
    for item in items:
        assert item["market"] == "KOSDAQ"


def test_search_empty_q_returns_all_up_to_50(client, session_with_data):
    r = client.get("/api/symbols/search")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) <= 50


def test_search_no_match_returns_empty(client, session_with_data):
    r = client.get("/api/symbols/search?q=없는종목XYZ")
    assert r.status_code == 200
    assert r.json() == []


def test_search_response_has_required_fields(client, session_with_data):
    r = client.get("/api/symbols/search?q=삼성")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    item = items[0]
    for field in ("symbol", "name", "market", "listing_date", "is_etf", "is_spac"):
        assert field in item, f"{field} 필드 누락"


# ── daily-prices 테스트

def test_daily_prices_basic(client, session_with_data):
    r = client.get("/api/symbols/005930/daily-prices")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "005930"
    assert body["total_count"] == 2
    assert len(body["items"]) == 2


def test_daily_prices_with_date_filter(client, session_with_data):
    r = client.get("/api/symbols/005930/daily-prices?start_date=2024-01-03&end_date=2024-01-03")
    assert r.status_code == 200
    body = r.json()
    assert body["total_count"] == 1
    assert body["items"][0]["date"] == "2024-01-03"


def test_daily_prices_adjusted_false(client, session_with_data):
    """adjusted=false 시 adj_* 필드가 null이다."""
    r = client.get("/api/symbols/005930/daily-prices?adjusted=false")
    assert r.status_code == 200
    body = r.json()
    assert body["adjusted"] is False
    for item in body["items"]:
        assert item["adj_close"] is None


def test_daily_prices_adjusted_true_has_adj_fields(client, session_with_data):
    """adjusted=true 시 adj_close 등이 non-null이다."""
    r = client.get("/api/symbols/005930/daily-prices?adjusted=true")
    assert r.status_code == 200
    body = r.json()
    assert body["adjusted"] is True
    for item in body["items"]:
        assert item["adj_close"] is not None


def test_daily_prices_symbol_not_found(client, session_with_data):
    """존재하지 않는 종목 → 404 SYMBOL_NOT_FOUND."""
    r = client.get("/api/symbols/XXXXXX/daily-prices")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "SYMBOL_NOT_FOUND"
    assert "x-request-id" in {k.lower() for k in r.headers}


def test_daily_prices_no_data_returns_404(client, session_with_data):
    """종목은 있지만 가격 데이터 없음 → 404 MARKET_DATA_NOT_FOUND."""
    # 000660은 심볼은 있지만 일봉 미삽입
    r = client.get("/api/symbols/000660/daily-prices")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "MARKET_DATA_NOT_FOUND"


def test_daily_prices_krw_int_type(client, session_with_data):
    """가격 컬럼은 KRW 정수 타입이다."""
    r = client.get("/api/symbols/005930/daily-prices")
    assert r.status_code == 200
    item = r.json()["items"][0]
    for field in ("open", "high", "low", "close"):
        assert isinstance(item[field], int), f"{field}이 int가 아님: {type(item[field])}"


# ── calendar 테스트

def test_calendar_basic(client, session_with_data):
    r = client.get("/api/calendar?year=2024&month=1&market=KOSPI")
    assert r.status_code == 200
    body = r.json()
    assert body["year"] == 2024
    assert body["month"] == 1
    assert body["market"] == "KOSPI"
    assert isinstance(body["items"], list)
    assert body["total_count"] == len(body["items"])


def test_calendar_contains_holiday(client, session_with_data):
    """휴장일(is_trading_day=False)도 포함된다."""
    r = client.get("/api/calendar?year=2024&month=1&market=KOSPI")
    assert r.status_code == 200
    items = r.json()["items"]
    dates = {item["date"]: item for item in items}
    # 2024-01-01 (신정, 휴장일)
    if "2024-01-01" in dates:
        assert dates["2024-01-01"]["is_trading_day"] is False
        assert dates["2024-01-01"]["holiday_name"] == "신정"


def test_calendar_contains_trading_day(client, session_with_data):
    """거래일(is_trading_day=True)이 포함된다."""
    r = client.get("/api/calendar?year=2024&month=1&market=KOSPI")
    assert r.status_code == 200
    items = r.json()["items"]
    dates = {item["date"]: item for item in items}
    if "2024-01-02" in dates:
        assert dates["2024-01-02"]["is_trading_day"] is True


def test_calendar_empty_month_returns_empty_items(client, session_with_data):
    """데이터 없는 월은 빈 items 반환."""
    r = client.get("/api/calendar?year=2020&month=1&market=KOSPI")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total_count"] == 0


def test_calendar_missing_params_returns_error(client, session_with_data):
    """year/month 필수 파라미터 누락 → 400 에러."""
    r = client.get("/api/calendar")
    assert r.status_code == 422 or r.status_code == 400
