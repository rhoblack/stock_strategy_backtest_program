"""DailyUpdateJob — 일일 증분 수집 + 영속화 (14번 §6.2).

매일 장 마감 후 (KST 18:00 권장, 본 step에서는 cron 메타만 보관) 다음을 수행한다:

1. 비거래일 체크 — trading_calendar에서 as_of_date가 거래일이 아니면 즉시 no-op return
2. 종목 마스터 갱신 (collect_symbols → upsert_symbol)
3. 거래일 캘린더 갱신 (collect_trading_calendar → upsert_trading_day)
4. 일봉 수집 (증분 판단 → collect_daily_prices → bulk_upsert_daily_prices)
   - symbol별 max(date) 조회 → 다음날부터 수집 (이미 최신이면 skip)
5. corporate_actions 적용 시 AdjustedPriceProcessor로 adj_* 재계산 (선택 — 입력 events 비어 있으면 1차 adj_* 그대로)
6. MissingDataCheckJob 호출로 결손 알림 (run() 마지막 단계)
7. JobResult로 통계 집계

설계 결정:

    1. **Collector / Processor / session_factory 의존성 주입** — 테스트 용이성
        - 운용 환경: PykrxCollector + AdjustedPriceProcessor + 실제 DB 세션
        - 테스트: MagicMock collector + 비어있는 events + in-memory SQLite

    2. **collect → process → load 단방향 흐름**
        - load(=DB 쓰기)는 016/026 repositories에 위임
        - 본 jobs는 오케스트레이터일 뿐, 비즈니스 로직 직접 보유 금지

    3. **결정론** (CLAUDE.md #8)
        - collector / processor 출력이 결정론이면 영속화 결과도 결정론
        - dict 순회 의존 금지 — collector 결과는 이미 (symbol ASC) 정렬

    4. **결손 알림** (14번 §13 / 14-k)
        - run() 마지막 단계에서 MissingDataCheckJob(db, notifier).run() 호출
        - 결손 카운트는 stats["missing_count"]에 누적

    5. **외부 fetch 정책**
        - 운용 환경에서만 collector가 외부 호출
        - 테스트는 collector를 MagicMock으로 교체 → 외부 호출 0건

    6. **비거래일 체크** (14번 §6.2)
        - trading_calendar에 as_of_date가 없거나 is_trading_day=False이면 즉시 return
        - no_op=True stats로 표기 (JobResult.success=True, stats["skipped_nontrading"]=1)

    7. **증분 판단** (14번 §6.2)
        - symbol별 daily_prices max(date) 조회
        - max(date) < as_of_date인 symbol만 수집 (이미 최신이면 skip)
        - 전체 target_symbols 중 수집 필요한 종목만 collector에 전달

14번 정책 매핑:
    - §3 (수집 대상) → collector 3-메서드 모두 호출
    - §6.2 (일일 증분) → 본 잡 자체 (비거래일 체크 + max(date) 증분 판단)
    - §7 (자동 검증) → collector 내부 validate=True 정책 (raise_on_hard_fail=True)
    - §9 (수정주가) → AdjustedPriceProcessor 적용 (corporate_actions 있으면)
    - §10 (결손 정책) → forward-fill 금지 (collector / processor가 이미 준수)
    - §13 (결손 알림) → MissingDataCheckJob 연동 + JobResult.warnings에 누적

13번 정책 매핑:
    - §7 (수정주가) — close 보존, adj_*만 재계산
    - §12 (결정론) — dict 순회 의존 금지
    - §15 (look-ahead) — as_of_date 이전 corporate_actions만 적용
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as date_type
from typing import TYPE_CHECKING

from app.data_pipeline.jobs.base import BaseJob, JobResult
from app.data_pipeline.processors.adjusted_price import (
    AdjustedPriceInput,
    AdjustedPriceProcessor,
    CorporateActionEvent,
)
from app.market_data import repositories

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

    from app.data_pipeline.collectors.base import BaseCollector


JOB_NAME = "daily_update"


@dataclass(frozen=True)
class DailyUpdateConfig:
    """DailyUpdateJob 설정.

    Attributes:
        as_of_date: 수집 기준일 (보통 어제 또는 오늘).
        markets: 거래일 캘린더 수집 대상 시장 리스트. 종목 마스터/시세는 collector의 markets 사용.
        symbols: 일봉 수집 대상 종목. None이면 collect_symbols 결과 전부.
        apply_adjusted_price: True면 AdjustedPriceProcessor로 재계산 (입력 events 빌드는 jobs가 책임).
        incremental: True면 symbol별 max(date) 기준 증분 수집. False면 as_of_date만 수집.
        run_missing_data_check: True면 영속화 후 MissingDataCheckJob 실행.
        check_trading_calendar: True면 as_of_date가 거래일이 아닐 때 즉시 no-op return.
    """

    as_of_date: date_type
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ")
    symbols: tuple[str, ...] | None = None
    apply_adjusted_price: bool = True
    incremental: bool = True
    run_missing_data_check: bool = False
    check_trading_calendar: bool = False


class DailyUpdateJob(BaseJob):
    """일일 증분 수집 + 영속화 잡 (14번 §6.2).

    Args:
        config: 수집 설정.
        collector: BaseCollector 구현체 (운용은 PykrxCollector, 테스트는 mock).
        session_factory: 호출할 때마다 새 Session을 반환하는 callable.
            트랜잭션 경계를 잡 내부에서 관리하기 위해 factory 주입 (테스트는 fixture로 주입).
        processor: AdjustedPriceProcessor (선택). None이면 기본 인스턴스 생성.
        name / schedule: BaseJob 메타.
        clock: 시작/종료 시각 측정용. 테스트에서 결정론을 위해 주입 가능.

    사용 예 (운용):
        job = DailyUpdateJob(
            config=DailyUpdateConfig(as_of_date=date.today()),
            collector=PykrxCollector(),
            session_factory=lambda: SessionLocal(),
        )
        result = job.run()

    사용 예 (테스트):
        mock_collector = MagicMock(spec=BaseCollector)
        mock_collector.collect_symbols.return_value = ...
        job = DailyUpdateJob(config=..., collector=mock_collector,
                             session_factory=lambda: db_session)
        result = job.run()
    """

    def __init__(
        self,
        config: DailyUpdateConfig,
        collector: BaseCollector,
        session_factory: Callable[[], Session],
        *,
        processor: AdjustedPriceProcessor | None = None,
        name: str = JOB_NAME,
        schedule: str | None = "0 18 * * 1-5",  # KST 평일 18시
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(name, schedule=schedule)
        self._config = config
        self._collector = collector
        self._session_factory = session_factory
        self._processor = processor or AdjustedPriceProcessor()
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self) -> JobResult:
        """수집 → 가공 → 영속화 흐름 실행.

        흐름:
            1. 비거래일 체크 (check_trading_calendar=True이면) — 비거래일이면 즉시 no-op return
            2. 종목 마스터 수집 / 영속화
            3. 거래일 캘린더 수집 / 영속화
            4. 증분 판단 (incremental=True이면) — symbol별 max(date) → 다음날부터 수집
            5. 일봉 수집 / 영속화
            6. 수정주가 재계산 (apply_adjusted_price=True이면)
            7. MissingDataCheckJob 결손 알림 (run_missing_data_check=True이면)

        오류는 가능한 한 JobResult.errors에 normalize. 단, 잡 단계 일반 오류
        (예: KeyError on dict)는 raise — 스케줄러가 잡아서 알림 발송.
        """
        started_at = self._clock()
        warnings: list[str] = []
        errors: list[str] = []
        stats = {
            "symbols_upserted": 0,
            "trading_days_upserted": 0,
            "daily_prices_upserted": 0,
            "events_applied": 0,
            "events_skipped": 0,
            "markets": len(self._config.markets),
            "skipped_nontrading": 0,
            "symbols_skipped_uptodate": 0,
            "missing_count": 0,
        }
        success = True

        try:
            # ----------------------------------------------------------------
            # Step 0: 비거래일 체크 (14번 §6.2)
            # ----------------------------------------------------------------
            if self._config.check_trading_calendar:
                with self._session_scope() as session:
                    is_trading = repositories.is_trading_day(
                        session,
                        date=self._config.as_of_date,
                        market=self._config.markets[0] if self._config.markets else "KOSPI",
                    )
                if not is_trading:
                    stats["skipped_nontrading"] = 1
                    warnings.append(
                        f"as_of_date {self._config.as_of_date.isoformat()} 은 거래일이 아님 "
                        f"(market={self._config.markets[0] if self._config.markets else 'KOSPI'}) "
                        f"— 수집 skip."
                    )
                    finished_at = self._clock()
                    return JobResult(
                        job_name=self.name,
                        success=True,
                        started_at=started_at,
                        finished_at=finished_at,
                        stats=tuple(
                            sorted(((k, int(v)) for k, v in stats.items()), key=lambda kv: kv[0])
                        ),
                        warnings=tuple(warnings),
                        errors=(),
                    )

            with self._session_scope() as session:
                # ----------------------------------------------------------------
                # Step 1: 종목 마스터 수집 / 영속화
                # ----------------------------------------------------------------
                symbols_data = self._collector.collect_symbols(self._config.as_of_date)
                warnings.extend(symbols_data.warnings)
                for row in symbols_data.rows:
                    repositories.upsert_symbol(
                        session,
                        {
                            "symbol": row.symbol,
                            "name": row.name,
                            "market": row.market,
                            "listing_date": row.listing_date,
                            "delisting_date": row.delisting_date,
                            "sector": row.sector,
                            "is_etf": row.is_etf,
                            "is_etn": row.is_etn,
                            "is_spac": row.is_spac,
                            "is_preferred": row.is_preferred,
                            "is_managed": row.is_managed,
                            "is_halted": row.is_halted,
                        },
                    )
                stats["symbols_upserted"] = len(symbols_data.rows)

                # ----------------------------------------------------------------
                # Step 2: 거래일 캘린더 수집 / 영속화 (시장별)
                # ----------------------------------------------------------------
                for market in self._config.markets:
                    cal_data = self._collector.collect_trading_calendar(
                        self._config.as_of_date, self._config.as_of_date, market
                    )
                    warnings.extend(cal_data.warnings)
                    for crow in cal_data.rows:
                        repositories.upsert_trading_day(
                            session,
                            date=crow.date,
                            market=crow.market,
                            is_trading_day=crow.is_trading_day,
                            holiday_name=crow.holiday_name,
                        )
                    stats["trading_days_upserted"] += len(cal_data.rows)

                # ----------------------------------------------------------------
                # Step 3: 일봉 수집 대상 결정
                # ----------------------------------------------------------------
                if self._config.symbols is not None:
                    target_symbols: tuple[str, ...] = tuple(sorted(self._config.symbols))
                else:
                    target_symbols = tuple(sorted(r.symbol for r in symbols_data.rows))

                # ----------------------------------------------------------------
                # Step 4: 증분 판단 (incremental=True) — symbol별 max(date) 조회
                # ----------------------------------------------------------------
                symbols_to_collect: tuple[str, ...]
                skipped_uptodate = 0
                if self._config.incremental and target_symbols:
                    needs_collect: list[str] = []
                    for symbol in target_symbols:
                        last_date = repositories.get_latest_price_date(session, symbol)
                        if last_date is None:
                            # DB에 데이터 없음 — 전체 수집 필요
                            needs_collect.append(symbol)
                        elif last_date < self._config.as_of_date:
                            # 아직 당일 데이터 없음 — 수집 필요
                            needs_collect.append(symbol)
                        else:
                            # last_date >= as_of_date → 이미 최신
                            skipped_uptodate += 1
                    symbols_to_collect = tuple(needs_collect)
                    stats["symbols_skipped_uptodate"] = skipped_uptodate
                else:
                    symbols_to_collect = target_symbols

                # ----------------------------------------------------------------
                # Step 5: 일봉 수집 / 영속화
                # ----------------------------------------------------------------
                if symbols_to_collect:
                    prices_data = self._collector.collect_daily_prices(
                        symbols_to_collect,
                        self._config.as_of_date,
                        self._config.as_of_date,
                    )
                    warnings.extend(prices_data.warnings)

                    # Step 6: 수정주가 재계산 (corporate_actions 있는 종목만)
                    if self._config.apply_adjusted_price:
                        events = self._collect_corporate_actions(
                            session, symbols_to_collect, self._config.as_of_date
                        )
                        if events:
                            proc_result = self._processor.process(
                                AdjustedPriceInput(
                                    prices=prices_data,
                                    corporate_actions=events,
                                    as_of_date=self._config.as_of_date,
                                )
                            )
                            warnings.extend(proc_result.warnings)
                            for issue in proc_result.validation.issues:
                                warnings.append(
                                    f"adjusted_price {issue.severity}: "
                                    f"{issue.code} — {issue.message}"
                                )
                            # process가 이벤트별 stats를 (key ASC) tuple로 반환
                            for k, v in proc_result.stats:
                                if k == "events_applied":
                                    stats["events_applied"] = v
                                elif k.startswith("events_skipped"):
                                    stats["events_skipped"] += v
                            rows_to_upsert = proc_result.output
                        else:
                            rows_to_upsert = prices_data.rows
                    else:
                        rows_to_upsert = prices_data.rows

                    # 영속화 (16/26 repositories)
                    upserted = repositories.bulk_upsert_daily_prices(
                        session,
                        rows=[
                            {
                                "symbol": r.symbol,
                                "date": r.date,
                                "open": r.open,
                                "high": r.high,
                                "low": r.low,
                                "close": r.close,
                                "volume": r.volume,
                                "adj_open": r.adj_open,
                                "adj_high": r.adj_high,
                                "adj_low": r.adj_low,
                                "adj_close": r.adj_close,
                                "adj_volume": r.adj_volume,
                                "market_cap": r.market_cap,
                            }
                            for r in rows_to_upsert
                        ],
                    )
                    stats["daily_prices_upserted"] = upserted

                session.commit()

            # ----------------------------------------------------------------
            # Step 7: MissingDataCheckJob 결손 알림 (14번 §13)
            # ----------------------------------------------------------------
            if self._config.run_missing_data_check:
                missing_count = self._run_missing_data_check(warnings)
                stats["missing_count"] = missing_count

        except Exception as exc:  # noqa: BLE001 — JobResult로 normalize
            success = False
            errors.append(f"{type(exc).__name__}: {exc}")

        finished_at = self._clock()
        return JobResult(
            job_name=self.name,
            success=success,
            started_at=started_at,
            finished_at=finished_at,
            stats=tuple(sorted(((k, int(v)) for k, v in stats.items()), key=lambda kv: kv[0])),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        """session_factory에서 새 세션을 받아 트랜잭션 경계로 감싼다."""
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def _run_missing_data_check(self, warnings: list[str]) -> int:
        """MissingDataCheckJob을 호출해 결손 알림 수집 후 missing_count 반환.

        14번 §13: 결손 알림은 영속화 후 별도 잡으로 수행.
        MissingDataCheckJob이 없거나 오류 발생 시 경고만 추가하고 0 반환 (non-fatal).
        """
        try:
            from app.data_pipeline.jobs.missing_data_check import (
                MissingDataCheckConfig,
                MissingDataCheckJob,
            )

            total_missing = 0
            for market in self._config.markets:
                check_config = MissingDataCheckConfig(
                    start_date=self._config.as_of_date,
                    end_date=self._config.as_of_date,
                    market=market,
                    symbols=self._config.symbols,
                )
                check_job = MissingDataCheckJob(
                    config=check_config,
                    session_factory=self._session_factory,
                    schedule=None,
                    clock=self._clock,
                )
                check_result = check_job.run()
                warnings.extend(check_result.warnings)
                total_missing += check_job.last_alert.missing_count
            return total_missing
        except Exception as exc:  # noqa: BLE001 — 결손 알림 실패는 non-fatal
            warnings.append(f"MissingDataCheckJob 실행 실패 (non-fatal): {exc}")
            return 0

    @staticmethod
    def _collect_corporate_actions(
        session: Session,
        symbols: tuple[str, ...],
        as_of_date: date_type,
    ) -> tuple[CorporateActionEvent, ...]:
        """대상 종목들의 corporate_actions를 ORM에서 dataclass로 변환.

        결정론: symbol ASC + (event_date ASC, event_type ASC) 정렬.
        14.9 look-ahead: end_date <= as_of_date.
        """
        events: list[CorporateActionEvent] = []
        for symbol in sorted(symbols):
            rows = repositories.get_corporate_actions(
                session, symbol, end_date=as_of_date
            )
            events.extend(
                CorporateActionEvent(
                    symbol=ca.symbol,
                    event_date=ca.event_date,
                    event_type=ca.event_type,
                    ratio=ca.ratio,
                    dividend_amount=ca.dividend_amount,
                )
                for ca in rows
            )
        return tuple(events)


__all__ = ["DailyUpdateConfig", "DailyUpdateJob", "JOB_NAME"]
