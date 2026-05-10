"""UniverseSnapshotJob — 019 UniverseSelector 결과를 027 universe_history에 영속화 (14번 §10).

백테스트 실행 시점 또는 사용자 미리보기에서 universe 스냅샷을 보존해 재현성/생존편향
영향 분석에 활용한다 (07번 §14, 13.13/14.10).

설계 결정:

    1. **UniverseSelector 의존성 주입** — 테스트 용이성
        - 운용은 UniverseSelector(session) 주입
        - 테스트는 mock UniverseSelector로 결과를 미리 만들어 주입

    2. **config_hash 안정 생성**
        - json.dumps(config, sort_keys=True, ensure_ascii=False) → SHA-256
        - 같은 config dict는 항상 같은 hash → UniqueConstraint 안정 매칭
        - dict 순회 의존 0건

    3. **결정론** (CLAUDE.md #8 / 13.12)
        - UniverseSelector.select_with_details 결과는 이미 (symbol ASC) 정렬
        - symbols_json은 그 순서 그대로 보존

    4. **scope** — 본 잡은 영속화 한 건만 (단일 as_of_date + 단일 config + 단일 market)
        - 여러 시점/시장은 호출자가 잡을 여러 번 호출

    5. **run_id** — 선택. backtest_runs와 연결 시 명시, preview 스냅샷이면 None.

14번 정책 매핑:
    - §10 생존편향 — symbols_json에 "그 시점에 살아있던 종목" 그대로 보존
    - §13 결손 알림 — universe 0건이면 warnings에 누적

13번 정책 매핑:
    - §13 (생존편향) — 폐지 종목도 보존 → 재현 시 생존편향 0
    - §15 (look-ahead) — UniverseSelector가 차단, jobs는 그 결과만 영속화
    - §12 (결정론) — config_hash 안정 생성 + symbols ASC
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import date as date_type
from typing import TYPE_CHECKING, Any

from app.data_pipeline.jobs.base import BaseJob, JobResult
from app.market_data import repositories
from app.market_data.universe import UniverseSelector

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session


JOB_NAME = "universe_snapshot"


def compute_config_hash(config: dict[str, Any]) -> str:
    """config dict의 안정 SHA-256 해시.

    json.dumps(sort_keys=True)로 dict 순회 의존 차단. ensure_ascii=False로 한글 키도 허용.
    """
    text = json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class UniverseSnapshotConfig:
    """UniverseSnapshotJob 설정.

    Attributes:
        as_of_date: universe 선정 기준일.
        selector_config: UniverseSelector에 전달할 config dict.
            (market / selection_method / exclude_* / min_market_cap / ... 등 06번 §8/§9)
        run_id: backtest_runs FK (선택). preview면 None.
    """

    as_of_date: date_type
    selector_config: dict[str, Any] = field(default_factory=dict)
    run_id: int | None = None


class UniverseSnapshotJob(BaseJob):
    """UniverseSelector → universe_history 영속화 잡 (14번 §10).

    Args:
        config: 스냅샷 설정.
        session_factory: 새 Session callable.
        selector_factory: session → UniverseSelector. 기본은 UniverseSelector(session).
            테스트는 mock factory 주입.
        name / schedule / clock: BaseJob 메타.
    """

    def __init__(
        self,
        config: UniverseSnapshotConfig,
        session_factory: Callable[[], Session],
        *,
        selector_factory: Callable[[Session], UniverseSelector] | None = None,
        name: str = JOB_NAME,
        schedule: str | None = None,  # 트리거 방식 (백테스트 실행 시 호출)
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(name, schedule=schedule)
        self._config = config
        self._session_factory = session_factory
        self._selector_factory = selector_factory or (
            lambda session: UniverseSelector(session)
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self) -> JobResult:
        started_at = self._clock()
        warnings: list[str] = []
        errors: list[str] = []
        stats = {
            "symbols_selected": 0,
            "snapshots_upserted": 0,
        }
        success = True

        try:
            with self._session_scope() as session:
                selector = self._selector_factory(session)
                result = selector.select_with_details(
                    self._config.selector_config, self._config.as_of_date
                )

                symbols_json = [s.symbol for s in result.symbols]
                stats["symbols_selected"] = len(symbols_json)

                if not symbols_json:
                    warnings.append(
                        f"universe 0건 — as_of_date={self._config.as_of_date.isoformat()} "
                        f"market={result.market} method={result.selection_method}"
                    )

                # 안정 해시 생성 (UniqueConstraint 키)
                config_hash = compute_config_hash(self._config.selector_config)

                repositories.upsert_universe_snapshot(
                    session,
                    {
                        "as_of_date": result.as_of_date,
                        "market": result.market,
                        "selection_method": result.selection_method,
                        "config_json": dict(self._config.selector_config),
                        "config_hash": config_hash,
                        "symbols_json": symbols_json,
                        "run_id": self._config.run_id,
                    },
                )
                stats["snapshots_upserted"] = 1

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


__all__ = [
    "JOB_NAME",
    "UniverseSnapshotConfig",
    "UniverseSnapshotJob",
    "compute_config_hash",
]
