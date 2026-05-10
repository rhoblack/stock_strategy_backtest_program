"""LocalCsvProvider 검증.

정책 매핑:
    - 13.7 (수정주가): close + adj_close 둘 다 NOT NULL — adj_close 빈 칸 시 명확한 에러
    - 13.13 / 14.10 (생존편향): delisting_date 빈 칸 → DB NULL, 폐지 종목 보존
    - 14.10 (결손 정책): 결손 봉 자동 채움 금지 — CSV에 없으면 DB에도 없음
    - 13.15 (look-ahead): 본 step은 적재만, look-ahead 차단은 PriceLoader/UniverseSelector
    - CLAUDE.md #8 (결정론): 입력 정렬 후 처리

외부 fetch: 0건 (네트워크 호출 없음).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.market_data import repositories
from app.market_data.local_csv import LocalCsvProvider
from app.market_data.provider import IngestResult

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "csv"


# ---------------------------------------------------------------------------
# 정상 적재
# ---------------------------------------------------------------------------


def test_ingest_into_loads_symbols(db_session):
    """sample fixture: 4개 종목 적재."""
    provider = LocalCsvProvider(root=FIXTURE_ROOT / "sample")
    result = provider.ingest_into(db_session)
    db_session.commit()

    assert isinstance(result, IngestResult)
    assert result.symbols_upserted == 4
    symbols = repositories.list_symbols(db_session)
    assert [s.symbol for s in symbols] == ["000660", "005930", "035720", "099999"]


def test_ingest_into_loads_daily_prices(db_session):
    """sample fixture: 3 종목 × 5 거래일 = 15 row."""
    provider = LocalCsvProvider(root=FIXTURE_ROOT / "sample")
    result = provider.ingest_into(db_session)
    db_session.commit()

    assert result.daily_prices_upserted == 15

    rows = repositories.get_price_range(
        db_session, "005930", date(2024, 1, 2), date(2024, 1, 8)
    )
    assert len(rows) == 5
    # 13.7: close + adj_close 모두 채워짐
    assert rows[0].close == 72100.0
    assert rows[0].adj_close == 72100.0
    assert rows[0].market_cap == 430000000000000.0


def test_ingest_into_loads_trading_calendar(db_session):
    """sample fixture: 8 캘린더 row (5 거래일 + 3 휴장)."""
    provider = LocalCsvProvider(root=FIXTURE_ROOT / "sample")
    result = provider.ingest_into(db_session)
    db_session.commit()

    assert result.trading_days_upserted == 8

    trading_days = repositories.get_trading_days(
        db_session, date(2024, 1, 1), date(2024, 1, 8)
    )
    # 5 거래일만 — 1/1 신정, 1/6/7 주말 제외
    assert trading_days == [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
    ]


# ---------------------------------------------------------------------------
# 13.13 / 14.10 생존편향 — 폐지 종목 보존
# ---------------------------------------------------------------------------


def test_delisting_date_preserved_for_delisted_symbol(db_session):
    """sample fixture의 099999는 delisting_date=2023-06-30. 보존되어야 함."""
    provider = LocalCsvProvider(root=FIXTURE_ROOT / "sample")
    provider.ingest_into(db_session)
    db_session.commit()

    delisted = repositories.get_symbol(db_session, "099999")
    assert delisted is not None
    assert delisted.delisting_date == date(2023, 6, 30)

    # 13.15: as_of_date 기준 미래에 있으면 universe에서 제외
    universe_2024 = repositories.get_universe_at_date(
        db_session, "KOSDAQ", date(2024, 1, 1)
    )
    assert "099999" not in [s.symbol for s in universe_2024]

    # 13.13: 폐지 이전 시점에는 universe에 포함되어야 (생존편향 차단)
    universe_2023 = repositories.get_universe_at_date(
        db_session, "KOSDAQ", date(2023, 1, 1)
    )
    assert "099999" in [s.symbol for s in universe_2023]


def test_active_symbol_has_null_delisting_date(db_session):
    """delisting_date 빈 칸은 NULL로 보존."""
    provider = LocalCsvProvider(root=FIXTURE_ROOT / "sample")
    provider.ingest_into(db_session)
    db_session.commit()

    samsung = repositories.get_symbol(db_session, "005930")
    assert samsung is not None
    assert samsung.delisting_date is None


# ---------------------------------------------------------------------------
# 13.7 수정주가 정책 — adj_close 누락 시 에러
# ---------------------------------------------------------------------------


def test_missing_adj_close_raises_value_error(db_session):
    """bad_missing_adj fixture: adj_close 빈 칸 → ValueError (13.7 강제)."""
    provider = LocalCsvProvider(root=FIXTURE_ROOT / "bad_missing_adj")
    with pytest.raises(ValueError, match="adj_close"):
        provider.ingest_into(db_session)


# ---------------------------------------------------------------------------
# 14.10 결손 정책 — forward-fill 금지
# ---------------------------------------------------------------------------


def test_missing_bar_not_filled(db_session):
    """with_missing fixture: 1/4 결손 봉 → DB에도 row 없음. forward-fill 금지."""
    provider = LocalCsvProvider(root=FIXTURE_ROOT / "with_missing")
    result = provider.ingest_into(db_session)
    db_session.commit()

    # CSV에 4행 → DB도 4행 (forward-fill 없음)
    assert result.daily_prices_upserted == 4
    rows = repositories.get_price_range(
        db_session, "005930", date(2024, 1, 1), date(2024, 1, 8)
    )
    assert [r.date.isoformat() for r in rows] == [
        "2024-01-02",
        "2024-01-03",
        "2024-01-05",
        "2024-01-08",
    ]
    # 1/4은 거래일이지만 daily_prices에 없음 (결손)
    missing = repositories.get_daily_price(db_session, "005930", date(2024, 1, 4))
    assert missing is None
    # 한편 trading_calendar에서는 거래일로 표기
    assert repositories.is_trading_day(db_session, date(2024, 1, 4)) is True


# ---------------------------------------------------------------------------
# 결정론
# ---------------------------------------------------------------------------


def test_ingest_is_idempotent(db_session):
    """동일 CSV를 두 번 적재해도 row 수 동일 (UniqueConstraint upsert)."""
    provider = LocalCsvProvider(root=FIXTURE_ROOT / "sample")
    provider.ingest_into(db_session)
    db_session.commit()

    second = provider.ingest_into(db_session)
    db_session.commit()

    # symbols / daily_prices / trading_calendar 모두 동일 (덮어씀)
    assert second.symbols_upserted == 4
    assert second.daily_prices_upserted == 15
    assert second.trading_days_upserted == 8

    rows = repositories.get_price_range(
        db_session, "005930", date(2024, 1, 2), date(2024, 1, 8)
    )
    assert len(rows) == 5  # 중복 row 없음


# ---------------------------------------------------------------------------
# symbol / 날짜 필터
# ---------------------------------------------------------------------------


def test_ingest_filters_by_symbols(db_session):
    """symbols 인자로 필터링."""
    provider = LocalCsvProvider(root=FIXTURE_ROOT / "sample")
    result = provider.ingest_into(db_session, symbols=["005930"])
    db_session.commit()

    assert result.symbols_upserted == 1
    assert result.daily_prices_upserted == 5
    symbols = repositories.list_symbols(db_session)
    assert [s.symbol for s in symbols] == ["005930"]


def test_ingest_filters_by_date_range(db_session):
    """start_date/end_date 인자로 daily_prices 필터링."""
    provider = LocalCsvProvider(root=FIXTURE_ROOT / "sample")
    result = provider.ingest_into(
        db_session,
        start_date=date(2024, 1, 3),
        end_date=date(2024, 1, 5),
    )
    db_session.commit()

    # 3 종목 × 3 거래일 (1/3, 1/4, 1/5)
    assert result.daily_prices_upserted == 9
    rows = repositories.get_price_range(
        db_session, "005930", date(2024, 1, 1), date(2024, 1, 31)
    )
    assert [r.date.isoformat() for r in rows] == ["2024-01-03", "2024-01-04", "2024-01-05"]


# ---------------------------------------------------------------------------
# 에러 케이스
# ---------------------------------------------------------------------------


def test_missing_root_raises(db_session, tmp_path):
    """존재하지 않는 디렉토리 → FileNotFoundError."""
    provider = LocalCsvProvider(root=tmp_path / "nonexistent")
    with pytest.raises(FileNotFoundError):
        provider.ingest_into(db_session)


def test_missing_symbols_csv_raises(db_session, tmp_path):
    """symbols.csv가 없으면 FileNotFoundError (필수 파일)."""
    (tmp_path / "empty").mkdir()
    provider = LocalCsvProvider(root=tmp_path / "empty")
    with pytest.raises(FileNotFoundError, match="symbols.csv"):
        provider.ingest_into(db_session)


def test_optional_csvs_missing_does_not_raise(db_session, tmp_path):
    """daily_prices.csv / trading_calendar.csv 없어도 OK — 0 row 적재."""
    root = tmp_path / "symbols_only"
    root.mkdir()
    (root / "symbols.csv").write_text(
        "symbol,name,market,listing_date\n005930,삼성전자,KOSPI,1975-06-11\n",
        encoding="utf-8",
    )
    provider = LocalCsvProvider(root=root)
    result = provider.ingest_into(db_session)
    db_session.commit()

    assert result.symbols_upserted == 1
    assert result.daily_prices_upserted == 0
    assert result.trading_days_upserted == 0


def test_missing_required_column_raises(db_session, tmp_path):
    """symbols.csv에 필수 컬럼(market) 누락 시 KeyError."""
    root = tmp_path / "bad_symbols"
    root.mkdir()
    (root / "symbols.csv").write_text(
        "symbol,name,listing_date\n005930,삼성전자,1975-06-11\n",
        encoding="utf-8",
    )
    provider = LocalCsvProvider(root=root)
    with pytest.raises(KeyError, match="market"):
        provider.ingest_into(db_session)
