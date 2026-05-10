"""data_pipeline 패키지 스켈레톤 검증 (Phase 11 step 024).

본 테스트는 ABC + dataclass + 예외 계층의 구조적 정합성만 검증한다.
실제 collector/processor/job 구현체 동작은 025~028 후속 step의 테스트에서 다룸.

검증 항목:
    1. 패키지 import 가능 + 공개 API 노출
    2. ABC subclass가 추상 메서드를 구현하지 않으면 TypeError
    3. frozen dataclass — 사후 변경 불가
    4. 예외 클래스 계층 + RetryableError.retry_after_seconds
    5. 결정론 헬퍼 — 같은 입력 같은 출력 (정렬)
    6. Scheduler — 잡 등록/조회/중복 방지

외부 fetch / DB 0건 — 모든 테스트는 in-memory.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from app.data_pipeline import (
    BaseCollector,
    BaseJob,
    BaseProcessor,
    CollectorError,
    DataPipelineError,
    DataValidationError,
    FatalError,
    JobError,
    JobResult,
    ProcessedResult,
    ProcessorError,
    RawCalendarData,
    RawCalendarRow,
    RawDailyPriceRow,
    RawDailyPricesData,
    RawSymbolRow,
    RawSymbolsData,
    RetryableError,
    Scheduler,
    ValidationIssue,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# A) 패키지 import 가능 / 공개 API 노출
# ---------------------------------------------------------------------------


def test_package_public_api_exposed() -> None:
    """본 step에서 약속한 공개 API가 모두 import 가능."""
    # 단순히 본 모듈이 import 성공한 것 자체로 검증되지만,
    # 명시적으로 한 번 더 참조해 누락 시 NameError를 빠르게 잡음.
    assert BaseCollector is not None
    assert BaseProcessor is not None
    assert BaseJob is not None
    assert Scheduler is not None
    assert DataPipelineError is not None


# ---------------------------------------------------------------------------
# B) ABC 강제 — abstract method 미구현 시 TypeError
# ---------------------------------------------------------------------------


def test_base_collector_cannot_instantiate_directly() -> None:
    with pytest.raises(TypeError):
        BaseCollector("test")  # type: ignore[abstract]


def test_base_processor_cannot_instantiate_directly() -> None:
    with pytest.raises(TypeError):
        BaseProcessor("test")  # type: ignore[abstract]


def test_base_job_cannot_instantiate_directly() -> None:
    with pytest.raises(TypeError):
        BaseJob("test")  # type: ignore[abstract]


def test_partial_collector_subclass_still_abstract() -> None:
    """3개 메서드 중 일부만 구현해도 인스턴스화 불가."""

    class _PartialCollector(BaseCollector):
        def collect_symbols(self, as_of_date):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        # collect_daily_prices, collect_trading_calendar 누락

    with pytest.raises(TypeError):
        _PartialCollector("partial")  # type: ignore[abstract]


def test_complete_collector_subclass_can_instantiate() -> None:
    """3개 메서드 모두 구현하면 인스턴스화 가능 (테스트용 더미 collector)."""

    class _DummyCollector(BaseCollector):
        def collect_symbols(self, as_of_date):  # type: ignore[no-untyped-def]
            return RawSymbolsData(
                rows=(),
                as_of_date=as_of_date,
                source="dummy",
            )

        def collect_daily_prices(self, symbols, start_date, end_date):  # type: ignore[no-untyped-def]
            return RawDailyPricesData(
                rows=(),
                start_date=start_date,
                end_date=end_date,
                source="dummy",
            )

        def collect_trading_calendar(self, start_date, end_date, market):  # type: ignore[no-untyped-def]
            return RawCalendarData(
                rows=(),
                start_date=start_date,
                end_date=end_date,
                market=market,
                source="dummy",
            )

    collector = _DummyCollector("dummy")
    assert collector.name == "dummy"
    result = collector.collect_symbols(date(2024, 1, 1))
    assert result.source == "dummy"
    assert result.rows == ()


# ---------------------------------------------------------------------------
# C) frozen dataclass — 사후 변경 불가
# ---------------------------------------------------------------------------


def test_raw_symbol_row_is_frozen() -> None:
    row = RawSymbolRow(
        symbol="005930",
        name="삼성전자",
        market="KOSPI",
        listing_date=date(1975, 6, 11),
    )
    with pytest.raises(FrozenInstanceError):
        row.name = "다른이름"  # type: ignore[misc]


def test_raw_daily_price_row_is_frozen() -> None:
    row = RawDailyPriceRow(
        symbol="005930",
        date=date(2024, 1, 2),
        open=70000,
        high=71000,
        low=69500,
        close=70500,
        volume=1_000_000,
        adj_open=70000,
        adj_high=71000,
        adj_low=69500,
        adj_close=70500,
        adj_volume=1_000_000,
    )
    with pytest.raises(FrozenInstanceError):
        row.close = 80000  # type: ignore[misc]


def test_raw_symbols_data_rows_is_tuple() -> None:
    """RawSymbolsData.rows는 tuple이어야 함 (결정론 + 불변)."""
    rs = RawSymbolsData(
        rows=(
            RawSymbolRow(symbol="000020", name="동화약품", market="KOSPI", listing_date=date(1976, 3, 1)),
            RawSymbolRow(symbol="005930", name="삼성전자", market="KOSPI", listing_date=date(1975, 6, 11)),
        ),
        as_of_date=date(2024, 1, 1),
        source="dummy",
    )
    assert isinstance(rs.rows, tuple)
    assert rs.warnings == ()


def test_processed_result_is_frozen() -> None:
    pr: ProcessedResult[tuple[int, ...]] = ProcessedResult(output=(1, 2, 3))
    with pytest.raises(FrozenInstanceError):
        pr.output = (4, 5, 6)  # type: ignore[misc]


def test_validation_result_counts() -> None:
    vr = ValidationResult(
        issues=(
            ValidationIssue(severity="hard_fail", code="OHLC_INCONSISTENT", message="high < low"),
            ValidationIssue(severity="soft_fail", code="MARKET_CAP_MISSING", message="cap=None"),
            ValidationIssue(severity="soft_fail", code="VOLUME_MISMATCH", message="±5%"),
        ),
        passed=False,
    )
    assert vr.hard_fail_count == 1
    assert vr.soft_fail_count == 2
    assert vr.passed is False


# ---------------------------------------------------------------------------
# D) 예외 계층
# ---------------------------------------------------------------------------


def test_exception_hierarchy() -> None:
    # 모든 예외가 DataPipelineError 루트
    assert issubclass(CollectorError, DataPipelineError)
    assert issubclass(ProcessorError, DataPipelineError)
    assert issubclass(JobError, DataPipelineError)
    assert issubclass(RetryableError, DataPipelineError)
    assert issubclass(FatalError, DataPipelineError)
    # DataValidationError는 ProcessorError 하위
    assert issubclass(DataValidationError, ProcessorError)
    assert issubclass(DataValidationError, DataPipelineError)


def test_retryable_error_carries_retry_after() -> None:
    err = RetryableError("rate limit", retry_after_seconds=5.0)
    assert err.retry_after_seconds == 5.0
    err_no_retry = RetryableError("default")
    assert err_no_retry.retry_after_seconds is None


def test_can_catch_all_via_data_pipeline_error() -> None:
    """호출자가 DataPipelineError 한 번에 모두 잡을 수 있어야 함 (단일 루트 검증)."""
    for exc_cls in (CollectorError, ProcessorError, JobError, FatalError, DataValidationError):
        with pytest.raises(DataPipelineError):
            raise exc_cls("test")
    # RetryableError는 생성자 시그니처가 다르므로 별도
    with pytest.raises(DataPipelineError):
        raise RetryableError("test", retry_after_seconds=1.0)


# ---------------------------------------------------------------------------
# E) 결정론 헬퍼 — 정렬 보장
# ---------------------------------------------------------------------------


def test_collector_sorted_symbol_helper() -> None:
    rows = [
        RawSymbolRow(symbol="005930", name="삼성전자", market="KOSPI", listing_date=date(1975, 6, 11)),
        RawSymbolRow(symbol="000020", name="동화약품", market="KOSPI", listing_date=date(1976, 3, 1)),
        RawSymbolRow(symbol="035420", name="네이버", market="KOSPI", listing_date=date(2002, 10, 29)),
    ]
    result = BaseCollector._to_sorted_symbol_tuple(rows)
    assert isinstance(result, tuple)
    assert [r.symbol for r in result] == ["000020", "005930", "035420"]


def test_collector_sorted_price_helper() -> None:
    rows = [
        RawDailyPriceRow(
            symbol="005930", date=date(2024, 1, 3),
            open=1, high=1, low=1, close=1, volume=1,
            adj_open=1, adj_high=1, adj_low=1, adj_close=1, adj_volume=1,
        ),
        RawDailyPriceRow(
            symbol="000020", date=date(2024, 1, 2),
            open=1, high=1, low=1, close=1, volume=1,
            adj_open=1, adj_high=1, adj_low=1, adj_close=1, adj_volume=1,
        ),
        RawDailyPriceRow(
            symbol="005930", date=date(2024, 1, 2),
            open=1, high=1, low=1, close=1, volume=1,
            adj_open=1, adj_high=1, adj_low=1, adj_close=1, adj_volume=1,
        ),
    ]
    result = BaseCollector._to_sorted_price_tuple(rows)
    assert [(r.symbol, r.date) for r in result] == [
        ("000020", date(2024, 1, 2)),
        ("005930", date(2024, 1, 2)),
        ("005930", date(2024, 1, 3)),
    ]


def test_collector_sorted_calendar_helper() -> None:
    rows = [
        RawCalendarRow(date=date(2024, 1, 3), market="KOSPI", is_trading_day=True),
        RawCalendarRow(date=date(2024, 1, 2), market="KOSDAQ", is_trading_day=True),
        RawCalendarRow(date=date(2024, 1, 2), market="KOSPI", is_trading_day=True),
    ]
    result = BaseCollector._to_sorted_calendar_tuple(rows)
    assert [(r.market, r.date) for r in result] == [
        ("KOSDAQ", date(2024, 1, 2)),
        ("KOSPI", date(2024, 1, 2)),
        ("KOSPI", date(2024, 1, 3)),
    ]


def test_processor_stats_to_tuple_is_sorted() -> None:
    stats = {"recalculated_rows": 100, "actions_applied": 5, "warnings_emitted": 2}
    result = BaseProcessor._stats_to_tuple(stats)
    assert result == (
        ("actions_applied", 5),
        ("recalculated_rows", 100),
        ("warnings_emitted", 2),
    )


def test_processor_context_to_tuple_is_sorted_strings() -> None:
    context = {"symbol": "005930", "date": date(2024, 1, 2), "ratio": 2}
    result = BaseProcessor._context_to_tuple(context)
    # key ASC 정렬, value는 모두 str로 캐스팅
    assert result == (("date", "2024-01-02"), ("ratio", "2"), ("symbol", "005930"))


# ---------------------------------------------------------------------------
# F) BaseJob + JobResult
# ---------------------------------------------------------------------------


def test_complete_job_subclass_can_instantiate_and_run() -> None:
    class _DummyJob(BaseJob):
        def run(self) -> JobResult:
            now = datetime(2026, 5, 10, tzinfo=UTC)
            return JobResult(
                job_name=self.name,
                success=True,
                started_at=now,
                finished_at=now,
                stats=(("rows", 0),),
            )

    job = _DummyJob("dummy_job", schedule="0 18 * * 1-5")
    assert job.name == "dummy_job"
    assert job.schedule == "0 18 * * 1-5"
    result = job.run()
    assert result.success is True
    assert result.stats == (("rows", 0),)
    assert result.duration_seconds == 0.0


def test_job_result_is_frozen() -> None:
    now = datetime(2026, 5, 10, tzinfo=UTC)
    jr = JobResult(job_name="x", success=True, started_at=now, finished_at=now)
    with pytest.raises(FrozenInstanceError):
        jr.success = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# G) Scheduler — 등록/조회/중복 방지/실행
# ---------------------------------------------------------------------------


class _NoopJob(BaseJob):
    def run(self) -> JobResult:
        now = datetime(2026, 5, 10, tzinfo=UTC)
        return JobResult(job_name=self.name, success=True, started_at=now, finished_at=now)


def test_scheduler_register_and_list_preserves_order() -> None:
    sch = Scheduler()
    sch.register(_NoopJob("a"))
    sch.register(_NoopJob("b"))
    sch.register(_NoopJob("c"))
    assert [j.name for j in sch.list_jobs()] == ["a", "b", "c"]


def test_scheduler_duplicate_registration_raises() -> None:
    sch = Scheduler()
    sch.register(_NoopJob("daily_update"))
    with pytest.raises(ValueError):
        sch.register(_NoopJob("daily_update"))


def test_scheduler_get_unknown_job_raises_keyerror() -> None:
    sch = Scheduler()
    with pytest.raises(KeyError):
        sch.get_job("missing")


def test_scheduler_run_job_dispatches() -> None:
    sch = Scheduler()
    sch.register(_NoopJob("hello"))
    result = sch.run_job("hello")
    assert result.job_name == "hello"
    assert result.success is True


# ---------------------------------------------------------------------------
# H) RawSymbolsData/RawDailyPricesData — frozen + tuple 필드
# ---------------------------------------------------------------------------


def test_raw_data_collections_are_frozen() -> None:
    rs = RawSymbolsData(rows=(), as_of_date=date(2024, 1, 1), source="dummy")
    with pytest.raises(FrozenInstanceError):
        rs.source = "other"  # type: ignore[misc]

    rp = RawDailyPricesData(
        rows=(), start_date=date(2024, 1, 1), end_date=date(2024, 1, 31), source="dummy"
    )
    with pytest.raises(FrozenInstanceError):
        rp.source = "other"  # type: ignore[misc]

    rc = RawCalendarData(
        rows=(),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        market="KOSPI",
        source="dummy",
    )
    with pytest.raises(FrozenInstanceError):
        rc.market = "KOSDAQ"  # type: ignore[misc]
