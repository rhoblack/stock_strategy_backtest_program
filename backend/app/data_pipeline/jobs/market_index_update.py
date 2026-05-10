"""MarketIndexJob — 시장 지수(KOSPI/KOSDAQ/...) 일봉 수집/영속화 (14번 §3-4 / §6.2).

024 BaseCollector ABC가 시장 지수 수집 메서드를 강제하지 않으므로 (3-메서드 분할:
symbols/prices/calendar) 본 잡은 명시적으로 `index_fetcher` callable을 주입받는다.

운용 환경에서는 PykrxCollector 또는 별도 IndexCollector 구현체에서 lambda로 위임:

    job = MarketIndexJob(
        config=MarketIndexConfig(
            index_codes=("KOSPI", "KOSDAQ"),
            start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
        ),
        index_fetcher=lambda code, start, end: pykrx_get_index_ohlcv(code, start, end),
        session_factory=SessionLocal,
    )

테스트 환경에서는 fetcher를 MagicMock으로 교체:

    fetcher = MagicMock(side_effect=fake_fetch)

설계 결정:

    1. **fetcher 시그니처**: `(index_code: str, start_date: date, end_date: date) -> Iterable[dict]`
        - dict 키: index_code / date / close (필수) + open/high/low/volume/change_pct (선택)
        - 027 repositories.upsert_market_index가 그대로 받음
        - 14.10 결손 정책: fetcher가 결손 봉을 반환하지 말 것 (forward-fill 금지)

    2. **결정론** (CLAUDE.md #8)
        - index_codes는 정렬해서 처리
        - fetcher 출력은 (date ASC, index_code ASC) 정렬 후 upsert (호출자 정렬 권장)

    3. **MARKET_INDEX_CODES enum 검증**
        - 알 수 없는 index_code → upsert_market_index에서 ValueError raise
        - JobResult.errors에 누적 (다른 index 처리는 계속)

14번 정책 매핑:
    - §3-4 시장 지수 수집 — 본 잡 자체
    - §10 결손 정책 — fetcher가 결손 봉 만들지 말 것 (jobs는 검증만)
    - §13 결손 알림 — JobResult.warnings에 누적
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as date_type
from typing import TYPE_CHECKING, Any

from app.data_pipeline.jobs.base import BaseJob, JobResult
from app.market_data import repositories

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session


JOB_NAME = "market_index_update"

# fetcher 시그니처 alias
IndexFetcher = Callable[
    [str, date_type, date_type],
    Iterable[Mapping[str, Any]],
]


@dataclass(frozen=True)
class MarketIndexConfig:
    """MarketIndexJob 설정.

    Attributes:
        index_codes: 수집 대상 지수 코드 (MARKET_INDEX_CODES 권장).
        start_date / end_date: 수집 구간 (포함).
    """

    index_codes: tuple[str, ...]
    start_date: date_type
    end_date: date_type

    def __post_init__(self) -> None:
        if not self.index_codes:
            raise ValueError("index_codes는 최소 1개 이상이어야 합니다.")
        if self.start_date > self.end_date:
            raise ValueError(
                f"start_date > end_date: "
                f"{self.start_date.isoformat()} > {self.end_date.isoformat()}"
            )


class MarketIndexJob(BaseJob):
    """시장 지수 일봉 수집/영속화 잡 (14번 §3-4 / §6.2).

    Args:
        config: 수집 설정.
        index_fetcher: (code, start, end) → Iterable[dict] (필수 키: index_code/date/close).
        session_factory: 새 Session callable.
        name / schedule / clock: BaseJob 메타.
    """

    def __init__(
        self,
        config: MarketIndexConfig,
        index_fetcher: IndexFetcher,
        session_factory: Callable[[], Session],
        *,
        name: str = JOB_NAME,
        schedule: str | None = "0 18 * * 1-5",  # KST 평일 18시
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(name, schedule=schedule)
        self._config = config
        self._fetcher = index_fetcher
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self) -> JobResult:
        started_at = self._clock()
        warnings: list[str] = []
        errors: list[str] = []
        stats = {
            "indices_processed": 0,
            "rows_upserted": 0,
            "rows_failed": 0,
        }
        success = True

        try:
            with self._session_scope() as session:
                # 결정론: index_codes 정렬 순회
                for code in sorted(self._config.index_codes):
                    try:
                        rows = list(
                            self._fetcher(
                                code, self._config.start_date, self._config.end_date
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        # 단일 지수 fetch 실패는 다른 지수 처리에 영향 없음
                        errors.append(f"index {code} fetch 실패: {type(exc).__name__}: {exc}")
                        continue

                    # 결정론: (date ASC, index_code ASC) 정렬 후 upsert
                    rows.sort(key=lambda r: (r.get("date"), str(r.get("index_code", code))))

                    for row in rows:
                        # row에 index_code 누락 시 config의 code로 보충
                        data = dict(row)
                        data.setdefault("index_code", code)
                        try:
                            repositories.upsert_market_index(session, data)
                            stats["rows_upserted"] += 1
                        except (KeyError, ValueError) as exc:
                            warnings.append(
                                f"index {code} row upsert 실패 ({type(exc).__name__}): {exc}"
                            )
                            stats["rows_failed"] += 1

                    stats["indices_processed"] += 1

                session.commit()

            # 잡 자체는 성공이지만 일부 fetch 실패가 있으면 success=False
            if errors:
                success = False
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


__all__ = ["IndexFetcher", "JOB_NAME", "MarketIndexConfig", "MarketIndexJob"]
