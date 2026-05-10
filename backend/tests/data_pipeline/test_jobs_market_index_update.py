"""MarketIndexJob 테스트 (Phase 11 step 028 / 14-j).

fetcher mock + in-memory SQLite로 영속화 검증.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.data_pipeline.jobs.market_index_update import (
    MarketIndexConfig,
    MarketIndexJob,
)
from app.models.market_index import MarketIndex


def _fake_fetcher(rows_by_code: dict[str, list[dict[str, Any]]]):
    """code → rows mapping으로 fetcher를 만든다."""

    def _f(code: str, start: date, end: date) -> list[dict[str, Any]]:
        return rows_by_code.get(code, [])

    return _f


def test_market_index_persists_multi_codes(session_factory) -> None:
    rows_by_code = {
        "KOSPI": [
            {"index_code": "KOSPI", "date": date(2024, 1, 2), "close": 2_650.0},
            {"index_code": "KOSPI", "date": date(2024, 1, 3), "close": 2_660.0},
        ],
        "KOSDAQ": [
            {"index_code": "KOSDAQ", "date": date(2024, 1, 2), "close": 880.0},
        ],
    }
    fetcher = _fake_fetcher(rows_by_code)
    job = MarketIndexJob(
        config=MarketIndexConfig(
            index_codes=("KOSPI", "KOSDAQ"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        ),
        index_fetcher=fetcher,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    stats = dict(result.stats)
    assert stats["indices_processed"] == 2
    assert stats["rows_upserted"] == 3
    assert stats["rows_failed"] == 0

    session = session_factory()
    try:
        all_idx = session.query(MarketIndex).order_by(
            MarketIndex.index_code, MarketIndex.date
        ).all()
        assert [(i.index_code, i.date, i.close) for i in all_idx] == [
            ("KOSDAQ", date(2024, 1, 2), 880.0),
            ("KOSPI", date(2024, 1, 2), 2_650.0),
            ("KOSPI", date(2024, 1, 3), 2_660.0),
        ]
    finally:
        session.close()


def test_market_index_processes_codes_in_sorted_order(session_factory) -> None:
    """index_codes는 sorted 순서로 fetcher 호출 (결정론)."""
    fetcher = MagicMock(return_value=[])
    job = MarketIndexJob(
        config=MarketIndexConfig(
            index_codes=("KOSPI200", "KOSPI", "KOSDAQ"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        ),
        index_fetcher=fetcher,
        session_factory=session_factory,
    )
    job.run()

    called_codes = [c.args[0] for c in fetcher.call_args_list]
    assert called_codes == sorted(("KOSPI200", "KOSPI", "KOSDAQ"))


def test_market_index_partial_fetcher_failure(session_factory) -> None:
    """단일 지수 fetcher 실패 → errors 누적, 다른 지수는 계속."""

    def _f(code: str, start: date, end: date) -> list[dict[str, Any]]:
        if code == "KOSDAQ":
            raise RuntimeError("KOSDAQ fetch 실패")
        return [{"index_code": code, "date": date(2024, 1, 2), "close": 2_650.0}]

    job = MarketIndexJob(
        config=MarketIndexConfig(
            index_codes=("KOSPI", "KOSDAQ"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        ),
        index_fetcher=_f,
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is False
    assert any("KOSDAQ fetch 실패" in e for e in result.errors)
    # KOSPI는 정상 영속화
    session = session_factory()
    try:
        kospi = session.query(MarketIndex).filter_by(index_code="KOSPI").all()
        assert len(kospi) == 1
    finally:
        session.close()


def test_market_index_invalid_code_warns(session_factory) -> None:
    """알 수 없는 index_code → upsert에서 ValueError → warnings 누적, success 유지."""
    rows_by_code = {
        "UNKNOWN": [{"index_code": "UNKNOWN", "date": date(2024, 1, 2), "close": 100.0}],
    }
    job = MarketIndexJob(
        config=MarketIndexConfig(
            index_codes=("UNKNOWN",),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        ),
        index_fetcher=_fake_fetcher(rows_by_code),
        session_factory=session_factory,
    )
    result = job.run()

    # fetcher는 성공했지만 upsert에서 실패 → success=True (errors 없음, warnings만)
    assert result.success is True
    assert any("UNKNOWN" in w for w in result.warnings)
    assert dict(result.stats)["rows_failed"] == 1


def test_market_index_invalid_config() -> None:
    with pytest.raises(ValueError, match="index_codes는 최소 1개"):
        MarketIndexConfig(
            index_codes=(), start_date=date(2024, 1, 1), end_date=date(2024, 1, 31)
        )
    with pytest.raises(ValueError, match="start_date > end_date"):
        MarketIndexConfig(
            index_codes=("KOSPI",),
            start_date=date(2024, 1, 31),
            end_date=date(2024, 1, 1),
        )


def test_market_index_determinism_repeated_runs(session_factory) -> None:
    rows = {
        "KOSPI": [{"index_code": "KOSPI", "date": date(2024, 1, 2), "close": 2_650.0}]
    }
    job = MarketIndexJob(
        config=MarketIndexConfig(
            index_codes=("KOSPI",),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        ),
        index_fetcher=_fake_fetcher(rows),
        session_factory=session_factory,
    )
    r1 = job.run()
    r2 = job.run()
    assert r1.stats == r2.stats
