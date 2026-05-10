"""market_data.repositories CRUD 검증.

검증 정책:
    - 13.7  : adj_close + close 둘 다 NOT NULL (스키마 강제 + 누락 시 KeyError)
    - 13.13 : 생존편향 — 폐지 종목도 보존, as_of_date 기반 동적 필터
    - 13.15 : look-ahead bias — 미래 상장 종목은 결과에서 제외
    - 14.10 : 결손 정책 — daily_prices에 row 없는 (symbol, date)는 None / get_price_range에서 누락
    - CLAUDE.md #8 : 정렬 결정론 — (date ASC, symbol ASC) tie-breaker
"""

from __future__ import annotations

from datetime import date

import pytest

from app.market_data import repositories
from app.models.daily_price import DailyPrice
from app.models.symbol import Symbol
from app.models.trading_calendar import TradingCalendar

# ---------------------------------------------------------------------------
# ORM 로드 / 모델 등록
# ---------------------------------------------------------------------------


def test_orm_models_load():
    """모델 import만으로 메타데이터에 등록되는지."""
    assert Symbol.__tablename__ == "symbols"
    assert DailyPrice.__tablename__ == "daily_prices"
    assert TradingCalendar.__tablename__ == "trading_calendar"


def test_init_db_creates_all_market_data_tables(db_engine):
    """models/__init__.py 등록 누락 검증 — init_db 후 3개 테이블이 모두 존재해야 함."""
    from sqlalchemy import inspect

    inspector = inspect(db_engine)
    tables = set(inspector.get_table_names())
    for tbl in ("symbols", "daily_prices", "trading_calendar"):
        assert tbl in tables, f"init_db에서 테이블 생성 안 됨: {tbl}"


# ---------------------------------------------------------------------------
# symbols
# ---------------------------------------------------------------------------


def _make_symbol_data(symbol="005930", **overrides):
    base = {
        "symbol": symbol,
        "name": "삼성전자",
        "market": "KOSPI",
        "listing_date": date(1975, 6, 11),
    }
    base.update(overrides)
    return base


def test_upsert_symbol_inserts_new(db_session):
    sym = repositories.upsert_symbol(db_session, _make_symbol_data())
    assert sym.symbol == "005930"
    assert sym.market == "KOSPI"
    assert sym.delisting_date is None  # 13.13: 활성 종목


def test_upsert_symbol_updates_existing(db_session):
    repositories.upsert_symbol(db_session, _make_symbol_data(name="원래이름"))
    updated = repositories.upsert_symbol(
        db_session, _make_symbol_data(name="새이름", is_managed=True)
    )
    assert updated.name == "새이름"
    assert updated.is_managed is True


def test_upsert_symbol_missing_required_key_raises(db_session):
    with pytest.raises(KeyError):
        repositories.upsert_symbol(db_session, {"name": "키없음"})


def test_get_symbol_returns_none_when_missing(db_session):
    assert repositories.get_symbol(db_session, "999999") is None


def test_get_symbol_returns_existing(db_session):
    repositories.upsert_symbol(db_session, _make_symbol_data())
    sym = repositories.get_symbol(db_session, "005930")
    assert sym is not None
    assert sym.symbol == "005930"


# ---------------------------------------------------------------------------
# 13.13 / 13.15 생존편향 + look-ahead — get_universe_at_date
# ---------------------------------------------------------------------------


def test_get_universe_at_date_excludes_future_listed(db_session):
    """13.15 — 미래 상장 종목은 as_of_date 기준으로 제외."""
    repositories.upsert_symbol(
        db_session,
        _make_symbol_data(symbol="111111", listing_date=date(2020, 1, 1)),
    )
    repositories.upsert_symbol(
        db_session,
        _make_symbol_data(symbol="222222", listing_date=date(2025, 1, 1)),
    )

    universe = repositories.get_universe_at_date(
        db_session, market="KOSPI", as_of_date=date(2022, 6, 1)
    )
    symbols = [s.symbol for s in universe]
    assert symbols == ["111111"]  # 222222는 미래 상장, 제외


def test_get_universe_at_date_excludes_already_delisted(db_session):
    """13.13 — 이미 폐지된 종목은 제외, 폐지 시점 이전 조회는 포함."""
    repositories.upsert_symbol(
        db_session,
        _make_symbol_data(
            symbol="333333",
            listing_date=date(2010, 1, 1),
            delisting_date=date(2021, 6, 1),
        ),
    )

    # 폐지 이전: 포함
    before = repositories.get_universe_at_date(
        db_session, market="KOSPI", as_of_date=date(2021, 5, 1)
    )
    assert [s.symbol for s in before] == ["333333"]

    # 폐지 당일/이후: 제외 (delisting_date > as_of_date 조건)
    on_delist = repositories.get_universe_at_date(
        db_session, market="KOSPI", as_of_date=date(2021, 6, 1)
    )
    assert on_delist == []

    after = repositories.get_universe_at_date(
        db_session, market="KOSPI", as_of_date=date(2022, 1, 1)
    )
    assert after == []


def test_get_universe_at_date_includes_active_symbol(db_session):
    """정상 활성 종목은 포함."""
    repositories.upsert_symbol(
        db_session,
        _make_symbol_data(symbol="444444", listing_date=date(2015, 1, 1)),
    )
    universe = repositories.get_universe_at_date(
        db_session, market="KOSPI", as_of_date=date(2024, 1, 1)
    )
    assert [s.symbol for s in universe] == ["444444"]


def test_get_universe_at_date_filters_by_market(db_session):
    repositories.upsert_symbol(
        db_session,
        _make_symbol_data(symbol="555555", market="KOSPI", listing_date=date(2010, 1, 1)),
    )
    repositories.upsert_symbol(
        db_session,
        _make_symbol_data(symbol="666666", market="KOSDAQ", listing_date=date(2010, 1, 1)),
    )
    kospi = repositories.get_universe_at_date(
        db_session, market="KOSPI", as_of_date=date(2024, 1, 1)
    )
    assert [s.symbol for s in kospi] == ["555555"]


def test_list_symbols_sorted_by_symbol_asc(db_session):
    """결정론 — symbol ASC."""
    for code in ("888888", "111111", "555555"):
        repositories.upsert_symbol(
            db_session,
            _make_symbol_data(symbol=code, listing_date=date(2010, 1, 1)),
        )
    out = repositories.list_symbols(db_session, market="KOSPI")
    assert [s.symbol for s in out] == ["111111", "555555", "888888"]


def test_list_symbols_empty_returns_empty_list(db_session):
    assert repositories.list_symbols(db_session) == []


def test_list_symbols_preserves_delisted_when_no_as_of_date(db_session):
    """13.13 폐지 종목 보존 — as_of_date 미지정 시 폐지 종목도 결과에 포함."""
    repositories.upsert_symbol(
        db_session,
        _make_symbol_data(
            symbol="777777",
            listing_date=date(2000, 1, 1),
            delisting_date=date(2010, 1, 1),
        ),
    )
    out = repositories.list_symbols(db_session)
    assert [s.symbol for s in out] == ["777777"]


# ---------------------------------------------------------------------------
# daily_prices
# ---------------------------------------------------------------------------


def _make_price_row(symbol="005930", d=date(2024, 1, 2), close=70000.0):
    """13.7 정책 따라 close + adj_close + 거래량 모두 채움."""
    return {
        "symbol": symbol,
        "date": d,
        "open": close - 100,
        "high": close + 100,
        "low": close - 200,
        "close": close,
        "volume": 1_000_000.0,
        "adj_open": close - 100,
        "adj_high": close + 100,
        "adj_low": close - 200,
        "adj_close": close,
        "adj_volume": 1_000_000.0,
        "market_cap": close * 1_000_000.0,
    }


def _seed_symbol(session, symbol="005930"):
    repositories.upsert_symbol(
        session, _make_symbol_data(symbol=symbol, listing_date=date(2000, 1, 1))
    )


def test_bulk_upsert_daily_prices_inserts(db_session):
    _seed_symbol(db_session)
    rows = [
        _make_price_row(d=date(2024, 1, 2), close=70000.0),
        _make_price_row(d=date(2024, 1, 3), close=71000.0),
    ]
    n = repositories.bulk_upsert_daily_prices(db_session, rows)
    assert n == 2
    fetched = repositories.get_price_range(
        db_session, "005930", date(2024, 1, 1), date(2024, 1, 31)
    )
    assert len(fetched) == 2
    assert fetched[0].close == 70000.0
    assert fetched[1].close == 71000.0


def test_bulk_upsert_daily_prices_updates_on_unique_collision(db_session):
    """UniqueConstraint(symbol, date) 위반 시 갱신."""
    _seed_symbol(db_session)
    repositories.bulk_upsert_daily_prices(
        db_session, [_make_price_row(d=date(2024, 1, 2), close=70000.0)]
    )
    repositories.bulk_upsert_daily_prices(
        db_session, [_make_price_row(d=date(2024, 1, 2), close=72000.0)]
    )
    p = repositories.get_daily_price(db_session, "005930", date(2024, 1, 2))
    assert p is not None
    assert p.close == 72000.0
    assert p.adj_close == 72000.0  # 13.7 정책 — 두 컬럼 모두 갱신


def test_bulk_upsert_daily_prices_missing_required_key_raises(db_session):
    _seed_symbol(db_session)
    bad = _make_price_row()
    del bad["adj_close"]  # 13.7 위반 — adj_close는 필수
    with pytest.raises(KeyError):
        repositories.bulk_upsert_daily_prices(db_session, [bad])


def test_bulk_upsert_daily_prices_sorts_input_for_determinism(db_session):
    """결정론 — 입력 순서 무관하게 (symbol ASC, date ASC) 처리."""
    for code in ("AAA", "BBB"):
        repositories.upsert_symbol(
            db_session,
            _make_symbol_data(symbol=code, listing_date=date(2000, 1, 1)),
        )
    rows = [
        _make_price_row(symbol="BBB", d=date(2024, 1, 5), close=200.0),
        _make_price_row(symbol="AAA", d=date(2024, 1, 3), close=100.0),
        _make_price_row(symbol="AAA", d=date(2024, 1, 2), close=99.0),
        _make_price_row(symbol="BBB", d=date(2024, 1, 4), close=199.0),
    ]
    n = repositories.bulk_upsert_daily_prices(db_session, rows)
    assert n == 4
    # 두 종목 모두 정상 적재
    aaa = repositories.get_price_range(db_session, "AAA", date(2024, 1, 1), date(2024, 1, 31))
    bbb = repositories.get_price_range(db_session, "BBB", date(2024, 1, 1), date(2024, 1, 31))
    assert [p.date for p in aaa] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert [p.date for p in bbb] == [date(2024, 1, 4), date(2024, 1, 5)]


def test_get_daily_price_returns_none_when_missing(db_session):
    """14.10 — 결손 봉(거래정지 등)은 row 없음, None 반환."""
    _seed_symbol(db_session)
    assert repositories.get_daily_price(db_session, "005930", date(2024, 1, 2)) is None


def test_get_price_range_sorted_by_date_asc(db_session):
    """결정론 — date ASC."""
    _seed_symbol(db_session)
    rows = [
        _make_price_row(d=date(2024, 1, 5)),
        _make_price_row(d=date(2024, 1, 2)),
        _make_price_row(d=date(2024, 1, 3)),
    ]
    repositories.bulk_upsert_daily_prices(db_session, rows)
    fetched = repositories.get_price_range(
        db_session, "005930", date(2024, 1, 1), date(2024, 1, 31)
    )
    assert [p.date for p in fetched] == [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 5),
    ]


def test_get_price_range_empty_when_no_data(db_session):
    """14.10 — 결손 구간은 빈 리스트 반환."""
    _seed_symbol(db_session)
    assert (
        repositories.get_price_range(
            db_session, "005930", date(2024, 1, 1), date(2024, 1, 31)
        )
        == []
    )


# ---------------------------------------------------------------------------
# trading_calendar
# ---------------------------------------------------------------------------


def test_upsert_trading_day_inserts(db_session):
    cal = repositories.upsert_trading_day(
        db_session, date(2024, 1, 2), "KOSPI", is_trading_day=True
    )
    assert cal.is_trading_day is True
    assert cal.holiday_name is None


def test_upsert_trading_day_updates_existing(db_session):
    repositories.upsert_trading_day(
        db_session, date(2024, 1, 2), "KOSPI", is_trading_day=True
    )
    repositories.upsert_trading_day(
        db_session,
        date(2024, 1, 2),
        "KOSPI",
        is_trading_day=False,
        holiday_name="신정",
    )
    cal = db_session.get(TradingCalendar, (date(2024, 1, 2), "KOSPI"))
    assert cal is not None
    assert cal.is_trading_day is False
    assert cal.holiday_name == "신정"


def test_is_trading_day_true(db_session):
    repositories.upsert_trading_day(
        db_session, date(2024, 1, 2), "KOSPI", is_trading_day=True
    )
    assert repositories.is_trading_day(db_session, date(2024, 1, 2)) is True


def test_is_trading_day_false_for_holiday(db_session):
    repositories.upsert_trading_day(
        db_session,
        date(2024, 1, 1),
        "KOSPI",
        is_trading_day=False,
        holiday_name="신정",
    )
    assert repositories.is_trading_day(db_session, date(2024, 1, 1)) is False


def test_is_trading_day_false_for_unknown_date(db_session):
    """캘린더 결손 → False (안전 측)."""
    assert repositories.is_trading_day(db_session, date(2024, 1, 2)) is False


def test_get_trading_days_sorted_asc(db_session):
    """결정론 — date ASC."""
    # 입력 순서 섞어서
    for d, is_td in (
        (date(2024, 1, 3), True),
        (date(2024, 1, 1), False),  # 신정
        (date(2024, 1, 2), True),
        (date(2024, 1, 4), True),
    ):
        repositories.upsert_trading_day(db_session, d, "KOSPI", is_trading_day=is_td)
    out = repositories.get_trading_days(
        db_session, date(2024, 1, 1), date(2024, 1, 31), market="KOSPI"
    )
    assert out == [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]


def test_get_trading_days_filters_market(db_session):
    repositories.upsert_trading_day(
        db_session, date(2024, 1, 2), "KOSPI", is_trading_day=True
    )
    repositories.upsert_trading_day(
        db_session, date(2024, 1, 2), "KOSDAQ", is_trading_day=False
    )
    kospi = repositories.get_trading_days(
        db_session, date(2024, 1, 1), date(2024, 1, 31), market="KOSPI"
    )
    kosdaq = repositories.get_trading_days(
        db_session, date(2024, 1, 1), date(2024, 1, 31), market="KOSDAQ"
    )
    assert kospi == [date(2024, 1, 2)]
    assert kosdaq == []


def test_get_trading_days_empty(db_session):
    assert (
        repositories.get_trading_days(
            db_session, date(2024, 1, 1), date(2024, 1, 31)
        )
        == []
    )


# ---------------------------------------------------------------------------
# FK ondelete=CASCADE — symbols 삭제 시 daily_prices 동반 삭제
# ---------------------------------------------------------------------------


def test_symbol_delete_cascades_to_daily_prices(db_session):
    _seed_symbol(db_session, "005930")
    repositories.bulk_upsert_daily_prices(
        db_session, [_make_price_row(d=date(2024, 1, 2))]
    )
    sym = repositories.get_symbol(db_session, "005930")
    assert sym is not None
    db_session.delete(sym)
    db_session.flush()
    # CASCADE — daily_prices도 삭제됨
    assert (
        repositories.get_daily_price(db_session, "005930", date(2024, 1, 2)) is None
    )
