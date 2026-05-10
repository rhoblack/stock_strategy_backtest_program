"""CorporateActionApplyJob — corporate_actions 변경 후 adj_* 일괄 재계산 (14번 §9 / §6.2).

신규 corporate_action이 등록되면 영향 받는 종목의 과거 adj_* 시계열 전부를
재계산해야 한다 (14.5 / 13.7 — 분할/배당 발생 시 과거 전체 재계산, 스냅샷 누적 금지).

본 잡은:
1. 영향 종목 리스트 (config.symbols)별로 과거 일봉 일괄 조회 (repositories.get_price_range)
2. 같은 종목의 corporate_actions 조회 (≤ end_date)
3. AdjustedPriceProcessor.process()로 adj_* 재계산
4. bulk_upsert_daily_prices로 영속화 (close 보존, adj_*만 갱신)

설계 결정:

    1. **collector 미사용** — DB에 이미 저장된 일봉을 입력으로 사용
        - get_price_range → ORM rows를 RawDailyPriceRow로 변환 → AdjustedPriceProcessor
        - 이로써 외부 fetch 0건. 본 잡은 순수하게 in-DB 재계산만.

    1.a. **14.5 / 13.7 — adj_*를 close로 reset 후 재계산 (idempotent 보장)**
        - DB의 adj_*는 이전 호출에서 누적 적용된 결과일 수 있으므로,
          본 잡은 매 호출마다 adj_* = close로 reset한 RawDailyPriceRow를 만들어
          AdjustedPriceProcessor 입력으로 전달
        - 이로써 동일 입력 동일 출력 (idempotent) 보장 — 잡 재실행해도 누적 적용 안 됨
        - 14.5 "분할/배당 발생 시 과거 전체 재계산" 정신과 일치 (스냅샷 누적 금지)

    2. **종목별 처리** — 한 잡 호출 = 여러 종목 일괄
        - Plan: jobs는 오케스트레이터, 종목별 루프 직접 보유
        - 트랜잭션은 잡 전체 단위 (실패 시 전체 롤백)

    3. **결정론** (CLAUDE.md #8)
        - 종목 처리 순서: sorted(symbols)
        - AdjustedPriceProcessor 자체가 결정론

    4. **look-ahead 차단** (13.15)
        - corporate_actions는 (event_date <= end_date)만 적용

14번 정책 매핑:
    - §9 (수정주가 재계산) — 본 잡 자체
    - §6.2 (일일 증분 — 4단계 corporate_actions 적용)
    - §10 (forward-fill 금지) — 입력 결손 봉은 그대로 결손 (재계산 안 함)
    - §13 (결손 알림) — 결손 봉은 본 잡이 만들지 않음 (MissingDataCheckJob 책임)

13번 정책 매핑:
    - §7 — close 보존, adj_*만 재계산
    - §15 — 미래 corporate_actions 적용 금지 (Processor가 차단)
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as date_type
from typing import TYPE_CHECKING

from app.data_pipeline.collectors.base import RawDailyPriceRow, RawDailyPricesData
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


JOB_NAME = "corporate_action_apply"

# 본 잡이 RawDailyPricesData에 채울 source 식별자
SOURCE_NAME = "corporate_action_apply_db"


@dataclass(frozen=True)
class CorporateActionApplyConfig:
    """CorporateActionApplyJob 설정.

    Attributes:
        symbols: 재계산 대상 종목.
        start_date / end_date: 재계산 범위 (포함). 보통 corporate_action 발생 이전 ~ 현재.
    """

    symbols: tuple[str, ...]
    start_date: date_type
    end_date: date_type

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("symbols는 최소 1개 이상이어야 합니다.")
        if self.start_date > self.end_date:
            raise ValueError(
                f"start_date > end_date: "
                f"{self.start_date.isoformat()} > {self.end_date.isoformat()}"
            )


class CorporateActionApplyJob(BaseJob):
    """corporate_actions 적용 후 adj_* 일괄 재계산 잡 (14번 §9).

    Args:
        config: 재계산 설정.
        session_factory: 새 Session callable.
        processor: AdjustedPriceProcessor (선택).
        name / schedule / clock: BaseJob 메타.
    """

    def __init__(
        self,
        config: CorporateActionApplyConfig,
        session_factory: Callable[[], Session],
        *,
        processor: AdjustedPriceProcessor | None = None,
        name: str = JOB_NAME,
        schedule: str | None = None,  # 트리거 방식 — corporate_action 등록 후 호출
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(name, schedule=schedule)
        self._config = config
        self._session_factory = session_factory
        self._processor = processor or AdjustedPriceProcessor()
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self) -> JobResult:
        started_at = self._clock()
        warnings: list[str] = []
        errors: list[str] = []
        stats = {
            "symbols_processed": 0,
            "rows_recalculated": 0,
            "events_applied": 0,
            "events_skipped": 0,
        }
        success = True

        try:
            with self._session_scope() as session:
                for symbol in sorted(self._config.symbols):
                    # 1) DB에서 과거 일봉 조회 (이미 저장된 데이터 — collector 미사용)
                    price_orm_rows = repositories.get_price_range(
                        session,
                        symbol=symbol,
                        start_date=self._config.start_date,
                        end_date=self._config.end_date,
                    )
                    if not price_orm_rows:
                        warnings.append(
                            f"종목 {symbol}: 재계산 범위에 일봉 0건 — skip"
                        )
                        continue

                    # 2) ORM → dataclass 변환
                    # 14.5 / 13.7 정합: 매 호출마다 close → adj_*로 reset해 누적 적용 차단
                    # (이미 adj_*에 factor가 누적된 상태에서 재호출하면 잘못됨 → 매번 원 가격에서 재계산)
                    raw_rows = tuple(
                        RawDailyPriceRow(
                            symbol=r.symbol,
                            date=r.date,
                            open=r.open,
                            high=r.high,
                            low=r.low,
                            close=r.close,
                            volume=r.volume,
                            # adj_* / adj_volume을 close / volume으로 reset
                            adj_open=r.open,
                            adj_high=r.high,
                            adj_low=r.low,
                            adj_close=r.close,
                            adj_volume=r.volume,
                            market_cap=r.market_cap,
                        )
                        for r in price_orm_rows
                    )
                    prices_input = RawDailyPricesData(
                        rows=raw_rows,
                        start_date=self._config.start_date,
                        end_date=self._config.end_date,
                        source=SOURCE_NAME,
                    )

                    # 3) corporate_actions 조회 + dataclass 변환
                    ca_orm_rows = repositories.get_corporate_actions(
                        session, symbol, end_date=self._config.end_date
                    )
                    if not ca_orm_rows:
                        warnings.append(
                            f"종목 {symbol}: corporate_actions 0건 — adj_* 변경 없음 skip"
                        )
                        continue

                    events = tuple(
                        CorporateActionEvent(
                            symbol=ca.symbol,
                            event_date=ca.event_date,
                            event_type=ca.event_type,
                            ratio=ca.ratio,
                            dividend_amount=ca.dividend_amount,
                        )
                        for ca in ca_orm_rows
                    )

                    # 4) Processor 호출
                    proc_result = self._processor.process(
                        AdjustedPriceInput(
                            prices=prices_input,
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
                            stats["events_applied"] += v
                        elif k.startswith("events_skipped"):
                            stats["events_skipped"] += v

                    # 5) bulk_upsert_daily_prices로 영속화 (close 보존, adj_*만 갱신)
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
                            for r in proc_result.output
                        ],
                    )
                    stats["rows_recalculated"] += upserted
                    stats["symbols_processed"] += 1

                session.commit()
        except Exception as exc:  # noqa: BLE001
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

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()


__all__ = ["CorporateActionApplyConfig", "CorporateActionApplyJob", "JOB_NAME"]
