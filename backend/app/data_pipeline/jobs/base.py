"""BaseJob 추상 인터페이스 (14번 §5 / §6 / §13 / §16).

본 모듈은 collectors/processors/repositories를 조합해 한 단위의 운영 작업을
실행하는 job의 공통 베이스를 정의한다.

설계 결정 (인계 정보 — 028 jobs 구현체가 따라야 함):

    1. **단일 `run() -> JobResult` 진입점**
        - cron/스케줄러는 이 메서드만 호출
        - 입력은 생성자에서 주입 (collector/processor/session_factory 등)
        - 결과는 항상 JobResult로 wrapping (예외 정보까지 포함)

    2. **JobResult dataclass (frozen)**
        - 성공/실패 + 통계 + 경고 + 시작/종료 시각
        - 예외 발생 시 raise 대신 JobResult.success=False + error 메시지로 normalize
          → 스케줄러가 단일 분기점만 보면 됨 (단, 잡 내부 오류로 인한 raise는 그대로 전파)

    3. **`name` / `schedule` 클래스 속성**
        - name: 잡 식별자 (로그/락 키)
        - schedule: cron string (None이면 수동 실행 전용)
        - 본 step에서는 메타만, 028에서 실제 cron 파싱/스케줄링 추가

    4. **외부 fetch 0건** (본 step)
        - ABC만, 실제 잡 (DailyUpdateJob / HistoricalBackfillJob / CorporateActionApplyJob)은 028
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class JobResult:
    """잡 실행 결과 (14번 §13 결손 알림 / §16 운영 체크리스트와 직결).

    Attributes:
        job_name: 어떤 잡의 결과인지.
        success: 잡 전체 성공 여부 (단일 hard_fail이라도 있으면 False).
        started_at / finished_at: 실행 시각 (UTC). 결정론을 위해 호출자 주입 가능.
        stats: 처리량/카운트 — 결정론 위해 (key ASC) 정렬된 tuple.
        warnings: 비치명적 경고.
        errors: 치명적 오류 메시지 (raise 대신 normalize한 경우).
    """

    job_name: str
    success: bool
    started_at: datetime
    finished_at: datetime
    stats: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


class BaseJob(ABC):
    """파이프라인 잡 추상 베이스 (14번 §5 jobs/).

    Args:
        name: 잡 식별자 — 로그/스케줄러 락 키로 사용. 결정론을 위해 영문/언더스코어 권장.
        schedule: cron string ("0 18 * * 1-5" 등) 또는 None (수동 실행 전용).
            본 step에서는 메타만 보관, 실제 파싱/실행은 028 Scheduler에서.

    Subclass 책임 (028 구현체가 따라야 함):
        - `run() -> JobResult` 구현
        - 내부에서 collector/processor/repositories 조합
        - 시작/종료 시각 기록 → JobResult에 포함
        - 14.7 검증 hard_fail 시 success=False + errors 누적
        - JobError / FatalError는 raise (스케줄러가 잡아서 알림 발송)
    """

    def __init__(self, name: str, *, schedule: str | None = None) -> None:
        self.name = name
        self.schedule = schedule

    @abstractmethod
    def run(self) -> JobResult:
        """잡 실행 메인 진입점.

        Returns:
            JobResult — 성공/실패 + 통계 + 경고/오류.

        Raises:
            JobError: 잡 단계 일반 오류 (의존 잡 미완료 등).
            FatalError: 영구 오류 — 스케줄러가 즉시 큐에서 제거.
        """


__all__ = ["BaseJob", "JobResult"]
