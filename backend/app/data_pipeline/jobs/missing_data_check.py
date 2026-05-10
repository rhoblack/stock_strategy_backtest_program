"""MissingDataCheckJob — 결손 알림 (14번 §13 / 14-k).

is_trading_day=true인데 daily_prices에 row가 없는 (symbol, date) 조합을 찾아
MissingDataAlert 형태로 보고한다. **forward-fill 절대 금지** (14.10) — 본 잡은
결손을 감지만 하며 자동으로 채우지 않는다.

설계 결정:

    1. **AlertResult dataclass (frozen)**
        - 결손 (symbol, date, market) 리스트
        - 결정론: (symbol ASC, date ASC) 정렬

    2. **JobResult.warnings**에 결손 카운트만 누적
        - 상세 결손 리스트는 AlertResult로 별도 반환 (캡처해 외부 알림 채널 연결 가능)
        - 본 step에서는 logger 미사용 (추후 14.13 알림 채널과 통합)

    3. **scope** — 단일 (start_date, end_date) 구간 + 단일 market + 종목 리스트
        - 종목 리스트 미지정 시 활성 종목 (listing/delisting 동적 필터) 전체 사용

    4. **결정론** (CLAUDE.md #8)
        - 거래일/종목 모두 정렬 후 처리

14번 정책 매핑:
    - §13 데이터 결손 알림 — 본 잡 자체
    - §10 결손 정책 (forward-fill 금지) — 본 잡은 채우지 않음, 감지만
    - §16.1 일일 점검 ([ ] 어제 일봉 수집 성공)

13번 정책 매핑:
    - §13 (생존편향) — listing_date / delisting_date 동적 필터 (016 list_symbols)
    - §15 (look-ahead) — end_date <= as_of_date 검사 권장 (호출자 책임)
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import date as date_type
from typing import TYPE_CHECKING

from app.data_pipeline.jobs.base import BaseJob, JobResult
from app.market_data import repositories

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session


JOB_NAME = "missing_data_check"


@dataclass(frozen=True)
class MissingDataEntry:
    """결손 단일 (symbol, date, market) 항목."""

    symbol: str
    date: date_type
    market: str


@dataclass(frozen=True)
class MissingDataAlert:
    """결손 알림 결과 (14번 §13).

    Attributes:
        entries: 결손 (symbol, date, market) — (symbol ASC, date ASC) 정렬.
        total_trading_days: 검사 구간 내 거래일 수.
        total_symbols: 검사 대상 종목 수.
        as_of_market: 검사 대상 시장.
    """

    entries: tuple[MissingDataEntry, ...] = field(default_factory=tuple)
    total_trading_days: int = 0
    total_symbols: int = 0
    as_of_market: str = ""

    @property
    def missing_count(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class MissingDataCheckConfig:
    """MissingDataCheckJob 설정.

    Attributes:
        start_date / end_date: 검사 구간 (포함).
        market: 검사 시장 (KOSPI / KOSDAQ / KONEX). 단일 시장만.
        symbols: 검사 종목. None이면 활성 종목 전체 (listing/delisting 동적 필터).
    """

    start_date: date_type
    end_date: date_type
    market: str = "KOSPI"
    symbols: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError(
                f"start_date > end_date: "
                f"{self.start_date.isoformat()} > {self.end_date.isoformat()}"
            )


class MissingDataCheckJob(BaseJob):
    """is_trading_day=true인데 daily_prices row가 없는 결손 감지 잡 (14번 §13 / 14-k).

    Args:
        config: 검사 설정.
        session_factory: 새 Session callable.
        name / schedule / clock: BaseJob 메타.

    사용 예:
        job = MissingDataCheckJob(
            config=MissingDataCheckConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                market="KOSPI",
            ),
            session_factory=SessionLocal,
        )
        result = job.run()
        # result.warnings: 결손 카운트 요약
        # job.last_alert: MissingDataAlert (상세 결손 리스트)
    """

    def __init__(
        self,
        config: MissingDataCheckConfig,
        session_factory: Callable[[], Session],
        *,
        name: str = JOB_NAME,
        schedule: str | None = "30 18 * * 1-5",  # KST 평일 18:30 (DailyUpdate 직후)
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(name, schedule=schedule)
        self._config = config
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        # 호출자가 detail을 캡처할 수 있도록 보존
        self.last_alert: MissingDataAlert = MissingDataAlert(
            as_of_market=self._config.market
        )

    def run(self) -> JobResult:
        started_at = self._clock()
        warnings: list[str] = []
        errors: list[str] = []
        stats = {
            "trading_days": 0,
            "symbols_checked": 0,
            "missing_count": 0,
            "missing_symbols": 0,
        }
        success = True
        entries: list[MissingDataEntry] = []

        try:
            with self._session_scope() as session:
                # 1) 검사 구간 거래일 수집 (016 trading_calendar)
                trading_days = repositories.get_trading_days(
                    session,
                    start_date=self._config.start_date,
                    end_date=self._config.end_date,
                    market=self._config.market,
                )
                stats["trading_days"] = len(trading_days)

                if not trading_days:
                    warnings.append(
                        f"검사 구간에 거래일 0건 — start={self._config.start_date.isoformat()} "
                        f"end={self._config.end_date.isoformat()} market={self._config.market}"
                    )
                else:
                    # 2) 검사 대상 종목 — 명시 시 그것만, 아니면 활성 종목 전체
                    target_symbols: tuple[str, ...]
                    if self._config.symbols is not None:
                        target_symbols = tuple(sorted(self._config.symbols))
                    else:
                        # listing_date <= end_date < (delisting_date or +inf)
                        active = repositories.list_symbols(
                            session,
                            market=self._config.market,
                            as_of_date=self._config.end_date,
                        )
                        target_symbols = tuple(sorted(s.symbol for s in active))
                    stats["symbols_checked"] = len(target_symbols)

                    # 3) 종목별로 결손 검사 — get_price_range로 존재 일자 set 만들고 trading_days와 차집합
                    missing_symbols_set: set[str] = set()
                    for symbol in target_symbols:
                        existing_rows = repositories.get_price_range(
                            session,
                            symbol=symbol,
                            start_date=self._config.start_date,
                            end_date=self._config.end_date,
                        )
                        existing_dates = {r.date for r in existing_rows}
                        missing_dates = sorted(set(trading_days) - existing_dates)
                        if missing_dates:
                            missing_symbols_set.add(symbol)
                            entries.extend(
                                MissingDataEntry(
                                    symbol=symbol,
                                    date=d,
                                    market=self._config.market,
                                )
                                for d in missing_dates
                            )

                    stats["missing_count"] = len(entries)
                    stats["missing_symbols"] = len(missing_symbols_set)

                    if entries:
                        warnings.append(
                            f"결손 감지: 총 {len(entries)}건 / "
                            f"{len(missing_symbols_set)}종목 "
                            f"(market={self._config.market}, "
                            f"trading_days={len(trading_days)})"
                        )

        except Exception as exc:  # noqa: BLE001
            success = False
            errors.append(f"{type(exc).__name__}: {exc}")

        # 결정론: (symbol ASC, date ASC) 정렬
        entries.sort(key=lambda e: (e.symbol, e.date))

        self.last_alert = MissingDataAlert(
            entries=tuple(entries),
            total_trading_days=stats["trading_days"],
            total_symbols=stats["symbols_checked"],
            as_of_market=self._config.market,
        )

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


__all__ = [
    "JOB_NAME",
    "MissingDataAlert",
    "MissingDataCheckConfig",
    "MissingDataCheckJob",
    "MissingDataEntry",
]
