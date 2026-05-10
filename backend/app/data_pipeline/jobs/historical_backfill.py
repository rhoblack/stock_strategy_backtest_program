"""HistoricalBackfillJob — 과거 N일 일괄 수집 (14번 §6.1).

초기 데이터 구축 또는 결손 재수집용. DailyUpdateJob과 흐름은 동일하지만
범위가 단일 일자가 아니라 (start_date, end_date) 구간이다.

설계 결정:

    1. **일자 단위 청크 처리 가능 — 본 step은 단일 호출**
        - collector.collect_daily_prices(symbols, start, end)에 (start, end) 그대로 전달
        - rate limit 분산이 필요하면 호출자가 구간을 쪼개 본 잡을 여러 번 호출
        - 본 step에서는 청크 분할 로직 미구현 (단순화)

    2. **종목 마스터 / 캘린더는 한 번만 수집**
        - 마스터는 `as_of_date=end_date` 기준 1회
        - 캘린더는 (start_date, end_date) 전체 범위 1회

    3. **수정주가 재계산** (선택)
        - apply_adjusted_price=True면 corporate_actions를 (≤end_date) 적용
        - 본 잡 자체가 백필이라 corporate_actions 누락이 흔함 → 호출자 책임

    4. **결정론** (CLAUDE.md #8 / 13.12)
        - DailyUpdateJob과 동일 정책

14번 정책 매핑:
    - §6.1 (초기 백필) — 본 잡 자체
    - §6.3 (재시도) — collector 위임
    - §10 (생존편향) — collector가 as_of_date 기준 활성 종목만 수집 (또는 호출자가 명시)
    - §13 (결손 알림) — JobResult.warnings에 누적

DailyUpdateJob과의 차이:
    - 단일 일자(=수집일) vs 구간(start, end)
    - 잡 이름 (logging / 락 키 분리)
    - 같은 collector / processor / repositories 재사용
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


JOB_NAME = "historical_backfill"


@dataclass(frozen=True)
class HistoricalBackfillConfig:
    """HistoricalBackfillJob 설정.

    Attributes:
        start_date / end_date: 수집 구간 (포함).
        markets: 캘린더 수집 대상.
        symbols: 일봉 수집 대상. None이면 collect_symbols 결과 전부.
        apply_adjusted_price: corporate_actions 기반 재계산 여부.
    """

    start_date: date_type
    end_date: date_type
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ")
    symbols: tuple[str, ...] | None = None
    apply_adjusted_price: bool = True

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError(
                f"start_date > end_date: "
                f"{self.start_date.isoformat()} > {self.end_date.isoformat()}"
            )


class HistoricalBackfillJob(BaseJob):
    """과거 N일 일괄 수집 잡 (14번 §6.1).

    Args / 사용 예는 DailyUpdateJob과 동일. cron schedule은 None (수동 실행 전용).
    """

    def __init__(
        self,
        config: HistoricalBackfillConfig,
        collector: BaseCollector,
        session_factory: Callable[[], Session],
        *,
        processor: AdjustedPriceProcessor | None = None,
        name: str = JOB_NAME,
        schedule: str | None = None,  # 백필은 수동
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(name, schedule=schedule)
        self._config = config
        self._collector = collector
        self._session_factory = session_factory
        self._processor = processor or AdjustedPriceProcessor()
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self) -> JobResult:
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
            "days_span": (self._config.end_date - self._config.start_date).days + 1,
        }
        success = True

        try:
            with self._session_scope() as session:
                # 1) 종목 마스터 (end_date 기준)
                symbols_data = self._collector.collect_symbols(self._config.end_date)
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

                # 2) 거래일 캘린더 (구간 전체)
                for market in self._config.markets:
                    cal_data = self._collector.collect_trading_calendar(
                        self._config.start_date, self._config.end_date, market
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

                # 3) 일봉 (구간 전체)
                target_symbols: tuple[str, ...]
                if self._config.symbols is not None:
                    target_symbols = self._config.symbols
                else:
                    target_symbols = tuple(r.symbol for r in symbols_data.rows)

                if target_symbols:
                    prices_data = self._collector.collect_daily_prices(
                        target_symbols,
                        self._config.start_date,
                        self._config.end_date,
                    )
                    warnings.extend(prices_data.warnings)

                    # 4) 수정주가 재계산 (선택)
                    if self._config.apply_adjusted_price:
                        events = self._collect_corporate_actions(
                            session, target_symbols, self._config.end_date
                        )
                        if events:
                            proc_result = self._processor.process(
                                AdjustedPriceInput(
                                    prices=prices_data,
                                    corporate_actions=events,
                                    as_of_date=self._config.end_date,
                                )
                            )
                            warnings.extend(proc_result.warnings)
                            for issue in proc_result.validation.issues:
                                warnings.append(
                                    f"adjusted_price {issue.severity}: "
                                    f"{issue.code} — {issue.message}"
                                )
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
    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
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


__all__ = ["HistoricalBackfillConfig", "HistoricalBackfillJob", "JOB_NAME"]
