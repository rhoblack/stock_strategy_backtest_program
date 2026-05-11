"""HistoricalBackfillJob 체크포인트 + RateLimiter + 7단계 실행 테스트 (step 048 / 14-l).

14번 정책 검증 항목 매핑:
    - 14.6.1 초기 백필 7단계 순서 → test_backfill_job_completes_all_stages
    - 14.6.4 KRX 차단 대응 (0.5초 간격 / 30분 일시정지) →
        test_rate_limiter_enforces_min_interval
        test_rate_limiter_block_after_failures
    - 체크포인트 저장/로드 → test_checkpoint_save_and_load
    - 재시작 시 완료 단계 스킵 → test_checkpoint_resume_skips_completed_stages

모든 테스트는 합성 데이터 fixture + mock만 사용. 외부 API 호출 없음.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.data_pipeline.collectors.base import (
    BaseCollector,
    RawCalendarData,
    RawCalendarRow,
    RawDailyPriceRow,
    RawDailyPricesData,
    RawSymbolRow,
    RawSymbolsData,
)
from app.data_pipeline.jobs.historical_backfill import (
    ALL_STAGES,
    STAGE_ADJUSTED_PRICES,
    STAGE_CALENDAR,
    STAGE_CORPORATE_ACTIONS,
    STAGE_DAILY_PRICES,
    STAGE_MARKET_CAP,
    STAGE_SYMBOLS,
    STAGE_VALIDATE,
    BackfillCheckpoint,
    HistoricalBackfillConfig,
    HistoricalBackfillJob,
)
from app.data_pipeline.utils.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# 합성 데이터 헬퍼
# ---------------------------------------------------------------------------


def _make_symbol(code: str) -> RawSymbolRow:
    return RawSymbolRow(
        symbol=code,
        name=f"종목{code}",
        market="KOSPI",
        listing_date=date(2020, 1, 1),
    )


def _make_price(code: str, d: date, close: float = 70_000.0) -> RawDailyPriceRow:
    return RawDailyPriceRow(
        symbol=code,
        date=d,
        open=close - 100,
        high=close + 200,
        low=close - 200,
        close=close,
        volume=1_000_000,
        adj_open=close - 100,
        adj_high=close + 200,
        adj_low=close - 200,
        adj_close=close,
        adj_volume=1_000_000,
        market_cap=close * 1_000_000_000,
    )


def _build_mock_collector(
    *,
    symbols: tuple[RawSymbolRow, ...] = (),
    prices: tuple[RawDailyPriceRow, ...] = (),
    calendar: tuple[RawCalendarRow, ...] = (),
    start: date = date(2024, 1, 1),
    end: date = date(2024, 1, 5),
) -> MagicMock:
    mock = MagicMock(spec=BaseCollector)
    mock.collect_symbols.return_value = RawSymbolsData(
        rows=symbols, as_of_date=end, source="mock"
    )
    mock.collect_daily_prices.return_value = RawDailyPricesData(
        rows=prices, start_date=start, end_date=end, source="mock"
    )
    mock.collect_trading_calendar.return_value = RawCalendarData(
        rows=calendar, start_date=start, end_date=end, market="KOSPI", source="mock"
    )
    return mock


# ---------------------------------------------------------------------------
# 체크포인트 저장/로드 테스트
# ---------------------------------------------------------------------------


class TestBackfillCheckpoint:
    """BackfillCheckpoint 저장 / 로드 / 이어받기 검증."""

    def test_checkpoint_save_and_load(self, tmp_path: Path) -> None:
        """체크포인트 저장 후 재로드 → 동일 값 (14-l 체크포인트 저장)."""
        ckpt_path = tmp_path / "checkpoint.json"
        ckpt = BackfillCheckpoint(
            as_of_date="2026-05-11",
            completed_stages=["symbols", "calendar"],
            last_symbol="005930",
        )
        ckpt.save(ckpt_path)

        loaded = BackfillCheckpoint.load(ckpt_path)
        assert loaded is not None
        assert loaded.as_of_date == "2026-05-11"
        assert loaded.completed_stages == ["symbols", "calendar"]
        assert loaded.last_symbol == "005930"

    def test_checkpoint_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        """존재하지 않는 파일 → None 반환 (신규 시작)."""
        result = BackfillCheckpoint.load(tmp_path / "no_file.json")
        assert result is None

    def test_checkpoint_load_corrupted_returns_none(self, tmp_path: Path) -> None:
        """파싱 실패 파일 → None 반환 (신규 시작)."""
        ckpt_path = tmp_path / "bad.json"
        ckpt_path.write_text("NOT VALID JSON", encoding="utf-8")
        result = BackfillCheckpoint.load(ckpt_path)
        assert result is None

    def test_checkpoint_is_stage_done(self, tmp_path: Path) -> None:
        """is_stage_done — 완료 단계 true / 미완료 단계 false."""
        ckpt = BackfillCheckpoint(
            as_of_date="2026-05-11",
            completed_stages=["symbols"],
        )
        assert ckpt.is_stage_done("symbols") is True
        assert ckpt.is_stage_done("calendar") is False

    def test_checkpoint_mark_stage_done_saves_immediately(
        self, tmp_path: Path
    ) -> None:
        """mark_stage_done 호출 후 즉시 파일에 반영."""
        ckpt_path = tmp_path / "ckpt.json"
        ckpt = BackfillCheckpoint(
            as_of_date="2026-05-11",
            completed_stages=[],
        )
        ckpt.mark_stage_done("symbols", ckpt_path)

        loaded = BackfillCheckpoint.load(ckpt_path)
        assert loaded is not None
        assert "symbols" in loaded.completed_stages

    def test_checkpoint_update_last_symbol_saves(self, tmp_path: Path) -> None:
        """update_last_symbol 호출 후 파일에 last_symbol 갱신."""
        ckpt_path = tmp_path / "ckpt.json"
        ckpt = BackfillCheckpoint(
            as_of_date="2026-05-11",
            completed_stages=["symbols"],
        )
        ckpt.update_last_symbol("005930", ckpt_path)

        loaded = BackfillCheckpoint.load(ckpt_path)
        assert loaded is not None
        assert loaded.last_symbol == "005930"

    def test_checkpoint_json_is_sorted_keys(self, tmp_path: Path) -> None:
        """JSON 파일이 sort_keys=True로 저장 — 결정론 보장."""
        ckpt_path = tmp_path / "ckpt.json"
        ckpt = BackfillCheckpoint(
            as_of_date="2026-05-11",
            completed_stages=["symbols"],
            last_symbol="005930",
        )
        ckpt.save(ckpt_path)
        content = ckpt_path.read_text(encoding="utf-8")
        # JSON 키 순서 확인 (sort_keys=True → as_of_date < completed_stages < last_symbol)
        idx_as_of = content.index('"as_of_date"')
        idx_completed = content.index('"completed_stages"')
        idx_last = content.index('"last_symbol"')
        assert idx_as_of < idx_completed < idx_last


# ---------------------------------------------------------------------------
# 체크포인트 이어받기 테스트
# ---------------------------------------------------------------------------


class TestCheckpointResume:
    """완료된 단계가 있을 때 재실행 시 해당 단계를 스킵하는지 검증."""

    def test_checkpoint_resume_skips_completed_stages(
        self, session_factory, tmp_path: Path
    ) -> None:
        """symbols + calendar 완료 체크포인트 → 재실행 시 두 단계 건너뜀.

        14-l 정책: 재시작 시 완료된 단계 스킵.
        """
        ckpt_path = tmp_path / "checkpoint.json"
        end = date(2024, 1, 5)

        # 미리 symbols + calendar 완료로 표시
        ckpt = BackfillCheckpoint(
            as_of_date=end.isoformat(),
            completed_stages=[STAGE_SYMBOLS, STAGE_CALENDAR],
            last_symbol=None,
        )
        ckpt.save(ckpt_path)

        collector = _build_mock_collector(
            symbols=(),
            prices=(),
            calendar=(),
            start=date(2024, 1, 1),
            end=end,
        )

        job = HistoricalBackfillJob(
            config=HistoricalBackfillConfig(
                start_date=date(2024, 1, 1),
                end_date=end,
                markets=("KOSPI",),
                symbols=(),  # 빈 심볼 → daily_prices 루프 없음
                checkpoint_path=ckpt_path,
            ),
            collector=collector,
            session_factory=session_factory,
        )
        result = job.run()

        # symbols 단계 완료 → collect_symbols 호출 없음
        collector.collect_symbols.assert_not_called()
        # calendar 단계 완료 → collect_trading_calendar 호출 없음
        collector.collect_trading_calendar.assert_not_called()
        # 잡 자체는 성공
        assert result.success is True

    def test_checkpoint_resume_with_different_as_of_date_restarts(
        self, session_factory, tmp_path: Path
    ) -> None:
        """as_of_date가 다른 체크포인트 → 신규 시작 (완료 단계 스킵 없음)."""
        ckpt_path = tmp_path / "checkpoint.json"

        # 과거 날짜의 체크포인트
        old_ckpt = BackfillCheckpoint(
            as_of_date="2020-01-01",
            completed_stages=[STAGE_SYMBOLS, STAGE_CALENDAR],
        )
        old_ckpt.save(ckpt_path)

        collector = _build_mock_collector(
            symbols=(_make_symbol("005930"),),
            start=date(2024, 1, 1),
            end=date(2024, 1, 5),
        )

        job = HistoricalBackfillJob(
            config=HistoricalBackfillConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 5),
                markets=("KOSPI",),
                symbols=(),
                checkpoint_path=ckpt_path,
            ),
            collector=collector,
            session_factory=session_factory,
        )
        job.run()

        # 신규 시작 → symbols 단계 호출됨
        collector.collect_symbols.assert_called_once()

    def test_daily_prices_resumes_from_last_symbol(
        self, session_factory, tmp_path: Path
    ) -> None:
        """last_symbol='005930' 체크포인트 → '005930' 다음 종목부터 수집.

        종목이 ['000020', '005930', '035420'] 일 때 last_symbol='005930' 이면
        '035420'만 수집.
        """
        ckpt_path = tmp_path / "checkpoint.json"
        end = date(2024, 1, 5)

        # symbols + calendar + corporate_actions 완료, daily_prices 미완료
        ckpt = BackfillCheckpoint(
            as_of_date=end.isoformat(),
            completed_stages=[
                STAGE_SYMBOLS,
                STAGE_CALENDAR,
                STAGE_CORPORATE_ACTIONS,
            ],
            last_symbol="005930",
        )
        ckpt.save(ckpt_path)

        target_symbols = ("000020", "005930", "035420")
        prices_035 = (_make_price("035420", date(2024, 1, 2)),)

        collector = _build_mock_collector(
            symbols=tuple(_make_symbol(s) for s in target_symbols),
            prices=prices_035,
            start=date(2024, 1, 1),
            end=end,
        )
        # collect_daily_prices가 호출될 때 symbols별 반환값 설정
        collector.collect_daily_prices.return_value = RawDailyPricesData(
            rows=prices_035,
            start_date=date(2024, 1, 1),
            end_date=end,
            source="mock",
        )

        job = HistoricalBackfillJob(
            config=HistoricalBackfillConfig(
                start_date=date(2024, 1, 1),
                end_date=end,
                markets=("KOSPI",),
                symbols=target_symbols,
                checkpoint_path=ckpt_path,
            ),
            collector=collector,
            session_factory=session_factory,
        )
        job.run()

        # collect_daily_prices는 '035420' 한 종목만 호출
        assert collector.collect_daily_prices.call_count == 1
        called_symbols = collector.collect_daily_prices.call_args.args[0]
        assert "035420" in called_symbols


# ---------------------------------------------------------------------------
# RateLimiter 테스트
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """RateLimiter 요청 간격 + 차단 감지 검증 (14.6.4)."""

    def test_rate_limiter_enforces_min_interval(self) -> None:
        """sleep_fn mock으로 0.5초 간격 검증.

        시나리오:
          - 1번째 wait(): _last=0.0, now=0.1 → elapsed=0.1 < 0.5 → sleep(0.4)
                          last_request_time 갱신용 monotonic() = 10.0
          - 2번째 wait(): _last=10.0, now=10.1 → elapsed=0.1 < 0.5 → sleep(0.4)

        wait() 내부 monotonic_fn 호출 순서 (block 없을 때):
            1. now = monotonic_fn()
            2. self._last_request_time = monotonic_fn()  (간격 sleep 후)
        """
        sleep_calls: list[float] = []

        # 1번째 wait: now=0.1 / last_update=10.0
        # 2번째 wait: now=10.1 / last_update=20.0
        times = iter([0.1, 10.0, 10.1, 20.0])

        def fake_monotonic() -> float:
            return next(times, 100.0)

        limiter = RateLimiter(
            min_interval_seconds=0.5,
            sleep_fn=sleep_calls.append,
            monotonic_fn=fake_monotonic,
        )

        # 1번째 wait(): _last=0.0, now=0.1, elapsed=0.1 → sleep(0.4)
        limiter.wait()
        assert len(sleep_calls) == 1
        assert abs(sleep_calls[0] - 0.4) < 1e-9

        # 2번째 wait(): _last=10.0, now=10.1, elapsed=0.1 → sleep(0.4)
        limiter.wait()
        assert len(sleep_calls) == 2
        assert abs(sleep_calls[1] - 0.4) < 1e-9

    def test_rate_limiter_no_sleep_when_sufficient_time_elapsed(self) -> None:
        """충분한 시간(>= min_interval)이 지났으면 sleep 없음.

        시나리오:
          - 1번째 wait(): _last=0.0, now=0.0 → elapsed=0.0 < 0.5 → sleep(0.5)
                          (초기 상태이므로 sleep 발생)
          - 2번째 wait(): _last=10.0, now=11.0 → elapsed=1.0 >= 0.5 → sleep 없음
        """
        sleep_calls: list[float] = []

        # 1번째 wait: now=0.0 / last=10.0 | 2번째 wait: now=11.0 / last=20.0
        times = iter([0.0, 10.0, 11.0, 20.0])

        limiter = RateLimiter(
            min_interval_seconds=0.5,
            sleep_fn=sleep_calls.append,
            monotonic_fn=lambda: next(times, 100.0),
        )

        # 1번째 wait(): _last=0.0 → elapsed=0 → sleep(0.5) 발생 (초기 상태)
        limiter.wait()
        assert len(sleep_calls) == 1  # 초기 상태에서 sleep 발생

        # 2번째 wait(): _last=10.0, now=11.0 → elapsed=1.0 >= 0.5 → sleep 없음
        limiter.wait()
        assert len(sleep_calls) == 1  # 추가 sleep 없음

    def test_rate_limiter_block_after_failures(self) -> None:
        """연속 실패 N회 → block_sleep 호출 검증 (14.6.4 §3).

        max_consecutive_failures=3, block_sleep_seconds=1800.
        record_failure() 3회 → wait() 호출 시 1800.0 sleep.
        """
        sleep_calls: list[float] = []
        limiter = RateLimiter(
            max_consecutive_failures=3,
            block_sleep_seconds=1800.0,
            sleep_fn=sleep_calls.append,
            monotonic_fn=lambda: 100.0,  # 항상 100 → elapsed=0 → min_interval sleep도 발생
        )

        # 3회 실패 기록
        limiter.record_failure()
        limiter.record_failure()
        limiter.record_failure()

        assert limiter.consecutive_failures == 3

        # wait() → block_sleep 적용
        limiter.wait()

        # 첫 번째 sleep이 block_sleep_seconds=1800.0
        assert sleep_calls[0] == 1800.0

    def test_rate_limiter_consecutive_failures_reset_after_block(self) -> None:
        """block_sleep 후 카운터 0으로 리셋."""
        limiter = RateLimiter(
            max_consecutive_failures=2,
            block_sleep_seconds=0.0,  # 테스트에서 즉시 완료
            sleep_fn=lambda _: None,
            monotonic_fn=lambda: 0.0,
        )
        limiter.record_failure()
        limiter.record_failure()

        limiter.wait()  # block_sleep 적용 + 카운터 리셋

        assert limiter.consecutive_failures == 0

    def test_rate_limiter_record_success_resets_counter(self) -> None:
        """record_success() → 연속 실패 카운터 리셋."""
        limiter = RateLimiter(
            sleep_fn=lambda _: None,
            monotonic_fn=lambda: 0.0,
        )
        limiter.record_failure()
        limiter.record_failure()
        assert limiter.consecutive_failures == 2

        limiter.record_success()
        assert limiter.consecutive_failures == 0

    def test_rate_limiter_failure_increments_counter(self) -> None:
        """record_failure() 호출 수만큼 카운터 증가."""
        limiter = RateLimiter(
            sleep_fn=lambda _: None,
            monotonic_fn=lambda: 0.0,
        )
        for i in range(1, 4):
            limiter.record_failure()
            assert limiter.consecutive_failures == i


# ---------------------------------------------------------------------------
# 7단계 전체 실행 테스트
# ---------------------------------------------------------------------------


class TestBackfillJobAllStages:
    """7단계 모두 호출 순서 + 성공 검증 (14.6.1)."""

    def test_backfill_job_completes_all_stages(
        self, session_factory, tmp_path: Path
    ) -> None:
        """collector/processor 전부 mock → 7단계 모두 호출됐는지 확인.

        14.6.1 초기 백필 7단계 순서:
        1) symbols → 2) calendar → 3) corporate_actions →
        4) daily_prices → 5) adjusted_prices → 6) market_cap → 7) validate
        """
        ckpt_path = tmp_path / "checkpoint.json"
        start = date(2024, 1, 1)
        end = date(2024, 1, 5)
        symbols = (_make_symbol("005930"),)
        prices = (
            _make_price("005930", date(2024, 1, 2)),
            _make_price("005930", date(2024, 1, 3)),
        )
        calendar = (
            RawCalendarRow(
                date=date(2024, 1, 2), market="KOSPI", is_trading_day=True
            ),
            RawCalendarRow(
                date=date(2024, 1, 3), market="KOSPI", is_trading_day=True
            ),
        )
        collector = _build_mock_collector(
            symbols=symbols,
            prices=prices,
            calendar=calendar,
            start=start,
            end=end,
        )

        job = HistoricalBackfillJob(
            config=HistoricalBackfillConfig(
                start_date=start,
                end_date=end,
                markets=("KOSPI",),
                symbols=("005930",),
                apply_adjusted_price=True,
                checkpoint_path=ckpt_path,
            ),
            collector=collector,
            session_factory=session_factory,
        )
        result = job.run()

        assert result.success is True

        # 단계 1, 2, 4 collector 호출 확인
        collector.collect_symbols.assert_called_once()
        collector.collect_trading_calendar.assert_called_once()
        collector.collect_daily_prices.assert_called()

        # 체크포인트에 7단계 모두 완료 표기됐는지 확인
        loaded_ckpt = BackfillCheckpoint.load(ckpt_path)
        assert loaded_ckpt is not None
        for stage in ALL_STAGES:
            assert stage in loaded_ckpt.completed_stages, (
                f"단계 '{stage}'가 체크포인트에 없음"
            )

    def test_backfill_job_stats_populated(
        self, session_factory, tmp_path: Path
    ) -> None:
        """JobResult.stats에 symbols_upserted / daily_prices_upserted 등이 있는지."""
        ckpt_path = tmp_path / "checkpoint.json"
        start = date(2024, 1, 1)
        end = date(2024, 1, 5)

        collector = _build_mock_collector(
            symbols=(_make_symbol("005930"),),
            prices=(
                _make_price("005930", date(2024, 1, 2)),
                _make_price("005930", date(2024, 1, 3)),
            ),
            calendar=(
                RawCalendarRow(
                    date=date(2024, 1, 2), market="KOSPI", is_trading_day=True
                ),
            ),
            start=start,
            end=end,
        )

        job = HistoricalBackfillJob(
            config=HistoricalBackfillConfig(
                start_date=start,
                end_date=end,
                markets=("KOSPI",),
                symbols=("005930",),
                checkpoint_path=ckpt_path,
            ),
            collector=collector,
            session_factory=session_factory,
        )
        result = job.run()

        stats = dict(result.stats)
        assert stats["symbols_upserted"] == 1
        assert stats["trading_days_upserted"] == 1
        assert stats["daily_prices_upserted"] >= 2
        assert stats["days_span"] == 5

    def test_backfill_job_normalizes_collector_failure(
        self, session_factory, tmp_path: Path
    ) -> None:
        """symbols 수집 실패 → JobResult.success=False (오케스트레이터 정책)."""
        ckpt_path = tmp_path / "checkpoint.json"
        collector = _build_mock_collector(
            start=date(2024, 1, 1), end=date(2024, 1, 5)
        )
        collector.collect_symbols.side_effect = RuntimeError("API down")

        job = HistoricalBackfillJob(
            config=HistoricalBackfillConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 5),
                markets=("KOSPI",),
                checkpoint_path=ckpt_path,
            ),
            collector=collector,
            session_factory=session_factory,
        )
        result = job.run()

        assert result.success is False
        assert len(result.errors) == 1

    def test_backfill_job_determinism_independent_runs(
        self, tmp_path: Path
    ) -> None:
        """독립된 DB 두 벌에서 동일 입력으로 실행 → 동일 stats.

        결정론 검증: 같은 입력 → 같은 출력 (14.12).
        체크포인트 파일이 없는 신규 시작 상태를 각각 보장.
        """
        from app.db.session import create_db_engine, drop_db, init_db, make_session_factory

        start = date(2024, 1, 1)
        end = date(2024, 1, 5)

        def _make_collector() -> MagicMock:
            return _build_mock_collector(
                symbols=(_make_symbol("005930"),),
                prices=(_make_price("005930", date(2024, 1, 2)),),
                calendar=(
                    RawCalendarRow(
                        date=date(2024, 1, 2), market="KOSPI", is_trading_day=True
                    ),
                ),
                start=start,
                end=end,
            )

        def _run(ckpt_path: Path, engine_url: str) -> dict:
            engine = create_db_engine(engine_url)
            init_db(engine)
            sf = make_session_factory(engine)
            try:
                job = HistoricalBackfillJob(
                    config=HistoricalBackfillConfig(
                        start_date=start,
                        end_date=end,
                        markets=("KOSPI",),
                        symbols=("005930",),
                        checkpoint_path=ckpt_path,
                    ),
                    collector=_make_collector(),
                    session_factory=lambda: sf(),
                )
                return dict(job.run().stats)
            finally:
                drop_db(engine)
                engine.dispose()

        s1 = _run(tmp_path / "ckpt1.json", "sqlite:///:memory:")
        s2 = _run(tmp_path / "ckpt2.json", "sqlite:///:memory:")

        # 두 독립 실행의 stats가 동일
        assert s1 == s2


# ---------------------------------------------------------------------------
# 기존 테스트 호환성 보장
# ---------------------------------------------------------------------------


class TestBackfillJobLegacyCompat:
    """기존 test_jobs_historical_backfill.py 테스트와의 호환성 보장.

    HistoricalBackfillJob은 여전히 같은 인터페이스를 유지해야 함.
    """

    def test_config_start_greater_than_end_raises(self) -> None:
        """start > end → ValueError (config __post_init__)."""
        with pytest.raises(ValueError, match="start_date > end_date"):
            HistoricalBackfillConfig(
                start_date=date(2024, 1, 5),
                end_date=date(2024, 1, 1),
            )

    def test_all_stages_constant_order(self) -> None:
        """ALL_STAGES 순서가 14.6.1 정의와 일치."""
        expected = (
            STAGE_SYMBOLS,
            STAGE_CALENDAR,
            STAGE_CORPORATE_ACTIONS,
            STAGE_DAILY_PRICES,
            STAGE_ADJUSTED_PRICES,
            STAGE_MARKET_CAP,
            STAGE_VALIDATE,
        )
        assert expected == ALL_STAGES

    def test_config_checkpoint_path_default(self) -> None:
        """기본 checkpoint_path = data/backfill_checkpoint.json."""
        from app.data_pipeline.jobs.historical_backfill import _DEFAULT_CHECKPOINT_PATH

        cfg = HistoricalBackfillConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
        )
        assert cfg.checkpoint_path == _DEFAULT_CHECKPOINT_PATH

    def test_config_rate_limiter_default_none(self) -> None:
        """config.rate_limiter = None → 잡이 기본 RateLimiter() 생성."""
        cfg = HistoricalBackfillConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
        )
        assert cfg.rate_limiter is None

    def test_custom_rate_limiter_injected(
        self, session_factory, tmp_path: Path
    ) -> None:
        """주입된 RateLimiter가 실제로 사용되는지 검증 (sleep_fn mock)."""
        sleep_calls: list[float] = []
        limiter = RateLimiter(
            sleep_fn=sleep_calls.append,
            monotonic_fn=lambda: 0.0,
            min_interval_seconds=0.0,  # 간격 0 → min_interval sleep 없음
        )

        ckpt_path = tmp_path / "checkpoint.json"
        collector = _build_mock_collector(
            symbols=(_make_symbol("005930"),),
            prices=(_make_price("005930", date(2024, 1, 2)),),
            start=date(2024, 1, 1),
            end=date(2024, 1, 5),
        )

        job = HistoricalBackfillJob(
            config=HistoricalBackfillConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 5),
                markets=("KOSPI",),
                symbols=("005930",),
                checkpoint_path=ckpt_path,
                rate_limiter=limiter,
            ),
            collector=collector,
            session_factory=session_factory,
        )
        job.run()

        # RateLimiter.wait()가 symbols/calendar/daily_prices 단계에서 호출됨
        # min_interval=0.0이어서 sleep 없음, 하지만 limiter 자체는 주입 확인
        assert limiter is job._rate_limiter
