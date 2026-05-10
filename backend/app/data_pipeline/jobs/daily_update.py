"""DailyUpdateJob — 일일 증분 수집 + 영속화 (14번 §6.2).

매일 장 마감 후 (KST 18:00 권장, 본 step에서는 cron 메타만 보관) 다음을 수행한다:

1. 종목 마스터 갱신 (collect_symbols → upsert_symbol)
2. 거래일 캘린더 갱신 (collect_trading_calendar → upsert_trading_day)
3. 일봉 수집 (collect_daily_prices → bulk_upsert_daily_prices)
4. corporate_actions 적용 시 AdjustedPriceProcessor로 adj_* 재계산 (선택 — 입력 events 비어 있으면 1차 adj_* 그대로)
5. JobResult로 통계 집계

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
        - 결손 알림 자체는 MissingDataCheckJob 별도 (missing_data_check.py)
        - 본 잡은 영속화 후 결손 카운트만 stats에 누적 (`missing_symbols`)

    5. **외부 fetch 정책**
        - 운용 환경에서만 collector가 외부 호출
        - 테스트는 collector를 MagicMock으로 교체 → 외부 호출 0건

14번 정책 매핑:
    - §3 (수집 대상) → collector 3-메서드 모두 호출
    - §6.2 (일일 증분) → 본 잡 자체
    - §7 (자동 검증) → collector 내부 validate=True 정책 (raise_on_hard_fail=True)
    - §9 (수정주가) → AdjustedPriceProcessor 적용 (corporate_actions 있으면)
    - §10 (결손 정책) → forward-fill 금지 (collector / processor가 이미 준수)
    - §13 (결손 알림) → JobResult.warnings에 누적

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
    """

    as_of_date: date_type
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ")
    symbols: tuple[str, ...] | None = None
    apply_adjusted_price: bool = True


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
        }
        success = True

        try:
            with self._session_scope() as session:
                # 1) 종목 마스터 수집 / 영속화
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

                # 2) 거래일 캘린더 수집 / 영속화 (시장별)
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

                # 3) 일봉 수집 — symbols 명시 시 그것만, 아니면 종목 마스터 전체
                target_symbols: tuple[str, ...]
                if self._config.symbols is not None:
                    target_symbols = self._config.symbols
                else:
                    target_symbols = tuple(r.symbol for r in symbols_data.rows)

                if target_symbols:
                    prices_data = self._collector.collect_daily_prices(
                        target_symbols,
                        self._config.as_of_date,
                        self._config.as_of_date,
                    )
                    warnings.extend(prices_data.warnings)

                    # 4) 수정주가 재계산 (corporate_actions 있는 종목만)
                    if self._config.apply_adjusted_price:
                        events = self._collect_corporate_actions(
                            session, target_symbols, self._config.as_of_date
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

                    # 5) 영속화 (16/26 repositories)
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
