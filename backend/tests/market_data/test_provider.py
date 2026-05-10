"""BaseProvider 인터페이스 검증.

본 모듈은 추상 베이스가 다음을 보장하는지 검증한다:
    - ingest_into 미구현 시 인스턴스화 불가 (ABC 보장)
    - 결정론 헬퍼(_sorted_*)가 (symbol, date) 정렬을 정확히 수행
    - IngestResult 누적/검증
"""

from __future__ import annotations

from datetime import date

import pytest

from app.market_data.provider import BaseProvider, IngestResult


class _MinimalProvider(BaseProvider):
    """테스트용 최소 구현 — ingest_into는 빈 결과 반환."""

    def ingest_into(
        self,
        session,
        *,
        symbols=None,
        start_date=None,
        end_date=None,
    ) -> IngestResult:
        return IngestResult()


def test_base_provider_is_abstract():
    """ingest_into 미구현 클래스는 인스턴스화 불가 (ABC 강제)."""

    class Incomplete(BaseProvider):  # type: ignore[misc]
        pass

    with pytest.raises(TypeError, match="abstract"):
        Incomplete(name="incomplete")  # type: ignore[abstract]


def test_base_provider_subclass_can_instantiate():
    provider = _MinimalProvider(name="minimal")
    assert provider.name == "minimal"


def test_ingest_result_default_values():
    result = IngestResult()
    assert result.symbols_upserted == 0
    assert result.daily_prices_upserted == 0
    assert result.trading_days_upserted == 0
    assert result.warnings == []
    assert result.total_rows == 0


def test_ingest_result_total_rows_sum():
    result = IngestResult(symbols_upserted=3, daily_prices_upserted=10, trading_days_upserted=5)
    assert result.total_rows == 18


def test_sorted_symbol_rows_alphabetical():
    """결정론: dict 순회 순서에 의존하지 않고 symbol ASC 정렬."""
    rows = [
        {"symbol": "035720"},
        {"symbol": "005930"},
        {"symbol": "000660"},
    ]
    sorted_rows = BaseProvider._sorted_symbol_rows(rows)
    assert [r["symbol"] for r in sorted_rows] == ["000660", "005930", "035720"]


def test_sorted_price_rows_symbol_then_date():
    """결정론: (symbol ASC, date ASC) tie-breaker."""
    rows = [
        {"symbol": "005930", "date": date(2024, 1, 5)},
        {"symbol": "000660", "date": date(2024, 1, 3)},
        {"symbol": "005930", "date": date(2024, 1, 2)},
        {"symbol": "000660", "date": date(2024, 1, 1)},
    ]
    sorted_rows = BaseProvider._sorted_price_rows(rows)
    assert [(r["symbol"], r["date"].isoformat()) for r in sorted_rows] == [
        ("000660", "2024-01-01"),
        ("000660", "2024-01-03"),
        ("005930", "2024-01-02"),
        ("005930", "2024-01-05"),
    ]


def test_sorted_calendar_rows_market_then_date():
    rows = [
        {"market": "KOSPI", "date": date(2024, 1, 3)},
        {"market": "KOSDAQ", "date": date(2024, 1, 2)},
        {"market": "KOSPI", "date": date(2024, 1, 2)},
    ]
    sorted_rows = BaseProvider._sorted_calendar_rows(rows)
    assert [(r["market"], r["date"].isoformat()) for r in sorted_rows] == [
        ("KOSDAQ", "2024-01-02"),
        ("KOSPI", "2024-01-02"),
        ("KOSPI", "2024-01-03"),
    ]
